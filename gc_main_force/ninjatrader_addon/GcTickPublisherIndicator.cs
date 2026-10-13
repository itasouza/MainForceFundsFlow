// ------------------------------------------------------------
// GcTickPublisherIndicator.cs — NinjaTrader 8 Indicator
// Gráfico GC → Indicators → GC Tick Publisher (TCP)
// TCP :5556 — uma linha JSON por tick (Last)
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
	public class GcTickPublisherIndicator : Indicator
	{
		private TcpListener _listener;
		private readonly ConcurrentDictionary<int, TcpClient> _clients = new ConcurrentDictionary<int, TcpClient>();
		private int _clientSeq;
		private CancellationTokenSource _cts;

		private long _ticksPublished;
		private long _ticksLastSecond;
		private int _lastSecond = -1;
		private double _lastPrice;
		private long _lastVolume;
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
				Description = "Publica ticks via TCP (JSON lines) para o Main Force Flow Python.";
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

		// Explicit Level-1 subscription (more reliable than only OnMarketData)
		private void OnInstrumentMarketData(object sender, MarketDataEventArgs e)
		{
			HandleLast(e);
		}

		protected override void OnMarketData(MarketDataEventArgs e)
		{
			HandleLast(e);
		}

		private void HandleLast(MarketDataEventArgs e)
		{
			if (!_listening)
				return;
			if (e == null || e.MarketDataType != MarketDataType.Last)
				return;

			double price = e.Price;
			long volume = e.Volume;
			// Some feeds send volume 0 on Last — still publish with vol=1 fallback for flow calc
			if (volume < 0)
				return;
			if (volume == 0)
				volume = 1;

			double bid = 0;
			double ask = 0;
			try
			{
				if (Instrument != null && Instrument.MarketData != null)
				{
					if (Instrument.MarketData.Bid != null)
						bid = Instrument.MarketData.Bid.Price;
					if (Instrument.MarketData.Ask != null)
						ask = Instrument.MarketData.Ask.Price;
				}
			}
			catch { }

			string symbol = "GC";
			try
			{
				if (Instrument != null && Instrument.MasterInstrument != null)
					symbol = Instrument.MasterInstrument.Name;
			}
			catch { }

			DateTime utc = e.Time.Kind == DateTimeKind.Utc ? e.Time : e.Time.ToUniversalTime();
			// Build JSON without nested {N:F2}}} braces (breaks String.Format on the last field)
			string json =
				"{\"timestamp\":\"" + utc.ToString("yyyy-MM-ddTHH:mm:ss.fff", CultureInfo.InvariantCulture) + "Z\"" +
				",\"symbol\":\"" + symbol + "\"" +
				",\"price\":" + price.ToString("F2", CultureInfo.InvariantCulture) +
				",\"volume\":" + volume.ToString(CultureInfo.InvariantCulture) +
				",\"bid\":" + bid.ToString("F2", CultureInfo.InvariantCulture) +
				",\"ask\":" + ask.ToString("F2", CultureInfo.InvariantCulture) +
				"}\n";

			Broadcast(Encoding.UTF8.GetBytes(json));
			Interlocked.Increment(ref _ticksPublished);
			Interlocked.Increment(ref _ticksLastSecond);
			_lastPrice = price;
			_lastVolume = volume;
			RefreshOverlay();
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
				"GC Tick Pub TCP:{0} | {1} | tps={2} | tot={3} | clients={4} | last={5:F2} x{6}",
				TcpPort, status, tps, Interlocked.Read(ref _ticksPublished),
				_clients.Count, _lastPrice, _lastVolume);

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
				Task.Run(() => AcceptLoop(_cts.Token));
				Print(string.Format("GC Tick Publisher LISTENING TCP:{0}", TcpPort));
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
