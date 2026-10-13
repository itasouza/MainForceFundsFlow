// ------------------------------------------------------------
// GcTickPublisherIndicator.cs — NinjaTrader 8 Indicator (TCP)
// Non-blocking: ConcurrentQueue + background worker (no socket I/O on MD thread)
// TCP :5556 — JSON lines for IncrementalMTFEngine (nt_tick_transport=tcp)
// ------------------------------------------------------------
#region Using declarations
using System;
using System.Collections.Concurrent;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
	internal sealed class TcpTickData
	{
		public DateTime TimestampUtc;
		public string Symbol;
		public double Price;
		public long Volume;
		public double Bid;
		public double Ask;
	}

	public class GcTickPublisherIndicator : Indicator
	{
		private TcpListener _listener;
		private readonly ConcurrentDictionary<int, TcpClient> _clients = new ConcurrentDictionary<int, TcpClient>();
		private readonly ConcurrentQueue<TcpTickData> _queue = new ConcurrentQueue<TcpTickData>();
		private const int MaxQueueSize = 50000;
		private int _clientSeq;
		private CancellationTokenSource _cts;
		private Task _acceptTask;
		private Task _publishTask;

		private long _ticksPublished;
		private long _ticksLastSecond;
		private long _dropped;
		private int _lastSecond = -1;
		private double _lastPrice;
		private long _lastVolume;
		private double _lastBid;
		private double _lastAsk;
		private bool _listening;
		private bool _hooked;

		[NinjaScriptProperty]
		[Range(1024, 65535)]
		[Display(Name = "TCP Port", Order = 1, GroupName = "Parameters")]
		public int TcpPort { get; set; }

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "Publica ticks via TCP (JSON lines) com ConcurrentQueue — não bloqueia OnMarketData.";
				Name = "GC Tick Publisher (TCP)";
				Calculate = Calculate.OnEachTick;
				IsOverlay = true;
				DisplayInDataBox = false;
				DrawOnPricePanel = true;
				PaintPriceMarkers = false;
				IsSuspendedWhileInactive = false;
				TcpPort = 5556;
			}
			else if (State == State.DataLoaded)
			{
				StartPublisher();
				HookMarketData();
			}
			else if (State == State.Terminated)
			{
				UnhookMarketData();
				StopPublisher();
			}
		}

		private void HookMarketData()
		{
			if (_hooked || Instrument == null || Instrument.MarketData == null)
				return;
			Instrument.MarketData.Update += OnInstrumentMarketData;
			_hooked = true;
			Print("GC Tick Publisher: MarketData.Update hooked on " + Instrument.FullName);
		}

		private void UnhookMarketData()
		{
			if (!_hooked || Instrument == null || Instrument.MarketData == null)
				return;
			try { Instrument.MarketData.Update -= OnInstrumentMarketData; } catch { }
			_hooked = false;
		}

		private void OnInstrumentMarketData(object sender, MarketDataEventArgs e)
		{
			EnqueueFromMarketData(e);
		}

		protected override void OnMarketData(MarketDataEventArgs e)
		{
			EnqueueFromMarketData(e);
		}

		/// <summary>CRITICAL: enqueue only — never socket Write on the MD thread.</summary>
		private void EnqueueFromMarketData(MarketDataEventArgs e)
		{
			if (!_listening || e == null)
				return;

			if (e.MarketDataType == MarketDataType.Bid)
			{
				_lastBid = e.Price;
				return;
			}
			if (e.MarketDataType == MarketDataType.Ask)
			{
				_lastAsk = e.Price;
				return;
			}
			if (e.MarketDataType != MarketDataType.Last)
				return;

			long volume = e.Volume;
			if (volume < 0)
				return;
			if (volume == 0)
				volume = 1;

			if (_queue.Count >= MaxQueueSize)
			{
				TcpTickData dropped;
				if (_queue.TryDequeue(out dropped))
					Interlocked.Increment(ref _dropped);
			}

			string symbol = "GC";
			try
			{
				if (Instrument != null && Instrument.MasterInstrument != null)
					symbol = Instrument.MasterInstrument.Name;
			}
			catch { }

			DateTime utc = e.Time.Kind == DateTimeKind.Utc ? e.Time : e.Time.ToUniversalTime();
			_queue.Enqueue(new TcpTickData
			{
				TimestampUtc = utc,
				Symbol = symbol,
				Price = e.Price,
				Volume = volume,
				Bid = _lastBid,
				Ask = _lastAsk
			});

			_lastPrice = e.Price;
			_lastVolume = volume;
		}

		protected override void OnBarUpdate()
		{
			RefreshOverlay();
		}

		private void RefreshOverlay()
		{
			int sec = DateTime.UtcNow.Second;
			long tps = Interlocked.Read(ref _ticksLastSecond);
			if (sec != _lastSecond)
			{
				_lastSecond = sec;
				tps = Interlocked.Exchange(ref _ticksLastSecond, 0);
			}

			string status = _listening ? "LISTENING" : "STOPPED";
			string text = string.Format(CultureInfo.InvariantCulture,
				"GC Tick Pub TCP:{0} | {1} | tps={2} | tot={3} | q={4} drop={5} | last={6:F2} x{7}",
				TcpPort, status, tps, Interlocked.Read(ref _ticksPublished),
				_queue.Count, Interlocked.Read(ref _dropped), _lastPrice, _lastVolume);

			Draw.TextFixed(this, "GcTickPubStatus", text, TextPosition.TopRight,
				_listening ? Brushes.LimeGreen : Brushes.OrangeRed,
				new Gui.Tools.SimpleFont("Arial", 12),
				Brushes.Transparent, Brushes.Transparent, 0);
		}

		private void StartPublisher()
		{
			try
			{
				_cts = new CancellationTokenSource();
				_listener = new TcpListener(IPAddress.Any, TcpPort);
				_listener.Start();
				_listening = true;
				_acceptTask = Task.Run(() => AcceptLoop(_cts.Token));
				_publishTask = Task.Factory.StartNew(
					() => PublishLoop(_cts.Token),
					_cts.Token,
					TaskCreationOptions.LongRunning,
					TaskScheduler.Default);
				Print(string.Format("GC Tick Publisher LISTENING TCP:{0} (queue+worker)", TcpPort));
				RefreshOverlay();
			}
			catch (Exception ex)
			{
				_listening = false;
				Print("GC Tick Publisher start failed: " + ex.Message);
			}
		}

		private void StopPublisher()
		{
			_listening = false;
			try
			{
				if (_cts != null)
				{
					_cts.Cancel();
					try { if (_publishTask != null) _publishTask.Wait(1500); } catch { }
					try { if (_acceptTask != null) _acceptTask.Wait(500); } catch { }
					_cts.Dispose();
					_cts = null;
				}
				if (_listener != null)
				{
					try { _listener.Stop(); } catch { }
					_listener = null;
				}
				foreach (var kv in _clients)
				{
					try { kv.Value.Close(); } catch { }
				}
				_clients.Clear();
				TcpTickData unused;
				while (_queue.TryDequeue(out unused)) { }
			}
			catch (Exception ex)
			{
				Print("GC Tick Publisher stop: " + ex.Message);
			}
		}

		private async Task AcceptLoop(CancellationToken token)
		{
			while (!token.IsCancellationRequested)
			{
				try
				{
					TcpClient client = await _listener.AcceptTcpClientAsync().ConfigureAwait(false);
					client.NoDelay = true;
					int id = Interlocked.Increment(ref _clientSeq);
					_clients[id] = client;
					Print("Python client connected #" + id);
				}
				catch (ObjectDisposedException) { break; }
				catch (Exception)
				{
					if (token.IsCancellationRequested) break;
					try { await Task.Delay(250, token).ConfigureAwait(false); } catch { break; }
				}
			}
		}

		private void PublishLoop(CancellationToken token)
		{
			while (!token.IsCancellationRequested)
			{
				TcpTickData tick;
				if (!_queue.TryDequeue(out tick))
				{
					Thread.Sleep(1);
					continue;
				}

				string json =
					"{\"timestamp\":\"" + tick.TimestampUtc.ToString("yyyy-MM-ddTHH:mm:ss.fff", CultureInfo.InvariantCulture) + "Z\"" +
					",\"symbol\":\"" + tick.Symbol + "\"" +
					",\"price\":" + tick.Price.ToString("F2", CultureInfo.InvariantCulture) +
					",\"volume\":" + tick.Volume.ToString(CultureInfo.InvariantCulture) +
					",\"bid\":" + tick.Bid.ToString("F2", CultureInfo.InvariantCulture) +
					",\"ask\":" + tick.Ask.ToString("F2", CultureInfo.InvariantCulture) +
					"}\n";

				byte[] payload = Encoding.UTF8.GetBytes(json);
				Broadcast(payload);
				Interlocked.Increment(ref _ticksPublished);
				Interlocked.Increment(ref _ticksLastSecond);
			}
		}

		private void Broadcast(byte[] payload)
		{
			foreach (var kv in _clients)
			{
				try
				{
					NetworkStream stream = kv.Value.GetStream();
					if (stream.CanWrite)
						stream.Write(payload, 0, payload.Length);
				}
				catch
				{
					TcpClient removed;
					_clients.TryRemove(kv.Key, out removed);
					try { if (removed != null) removed.Close(); } catch { }
				}
			}
		}
	}
}
