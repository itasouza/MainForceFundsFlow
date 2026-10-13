// ------------------------------------------------------------
// GcTickPublisher.cs — NinjaTrader 8 Add-On (production)
// Non-blocking tick export: ConcurrentQueue + background NetMQ PUB
// Endpoint: tcp://*:5556  Topic: gc_ticks
// JSON schema matches IncrementalMTFEngine / NtTickSubscriber
// ------------------------------------------------------------
#region Using declarations
using System;
using System.Collections.Concurrent;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NetMQ;
using NetMQ.Sockets;
#endregion

namespace NinjaTrader.NinjaScript.AddOns
{
	/// <summary>Immutable tick snapshot queued from the market-data thread.</summary>
	internal sealed class TickData
	{
		public DateTime TimestampUtc;
		public string Symbol;
		public double Price;
		public long Volume;
		public double Bid;
		public double Ask;
	}

	public class GcTickPublisher : AddOnBase
	{
		// ---- config ----
		private string _instrumentName = "GC";
		private string _bindAddress = "tcp://*:5556";
		private string _topic = "gc_ticks";
		private const int MaxQueueSize = 50000;

		// ---- market ----
		private Instrument _instrument;
		private double _lastBid;
		private double _lastAsk;
		private bool _marketHooked;

		// ---- queue / worker ----
		private readonly ConcurrentQueue<TickData> _queue = new ConcurrentQueue<TickData>();
		private CancellationTokenSource _cts;
		private Task _workerTask;
		private PublisherSocket _pub;
		private readonly object _socketLock = new object();

		// ---- stats / UI ----
		private long _enqueued;
		private long _published;
		private long _dropped;
		private long _publishedLastSecond;
		private double _lastPrice;
		private long _lastVolume;
		private bool _connected;
		private NTWindow _window;
		private TextBlock _statusText;
		private TextBlock _tpsText;
		private TextBlock _queueText;
		private TextBlock _lastTickText;
		private DispatcherTimer _uiTimer;
		private NTMenuItem _menuItem;
		private NTMenuItem _newMenu;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "High-performance GC tick publisher (ConcurrentQueue + NetMQ PUB) for Main Force Flow Python engine.";
				Name = "GC Tick Publisher ZMQ";
			}
			else if (State == State.Terminated)
			{
				StopEverything();
			}
		}

		protected override void OnWindowCreated(Window window)
		{
			ControlCenter cc = window as ControlCenter;
			if (cc == null)
				return;

			_newMenu = cc.FindFirst("ControlCenterMenuItemNew") as NTMenuItem;
			if (_newMenu == null)
				return;

			foreach (object item in _newMenu.Items)
			{
				NTMenuItem mi = item as NTMenuItem;
				if (mi != null && mi.Header != null && mi.Header.ToString() == "GC Tick Publisher ZMQ")
					return;
			}

			_menuItem = new NTMenuItem
			{
				Header = "GC Tick Publisher ZMQ",
				Style = Application.Current.TryFindResource("MainMenuItem") as Style
			};
			_menuItem.Click += OnMenuItemClick;
			_newMenu.Items.Add(_menuItem);
		}

		protected override void OnWindowDestroyed(Window window)
		{
			if (window is ControlCenter && _menuItem != null && _newMenu != null)
			{
				_menuItem.Click -= OnMenuItemClick;
				_newMenu.Items.Remove(_menuItem);
				_menuItem = null;
			}
			if (_window != null && ReferenceEquals(window, _window))
				_window = null;
		}

		private void OnMenuItemClick(object sender, RoutedEventArgs e)
		{
			StartPublisher();
			ShowOrFocusWindow();
		}

		private void StartPublisher()
		{
			if (_cts != null && !_cts.IsCancellationRequested)
			{
				EnsureMarketData();
				return;
			}

			try
			{
				_cts = new CancellationTokenSource();
				lock (_socketLock)
				{
					_pub = new PublisherSocket();
					_pub.Options.SendHighWatermark = 10000;
					_pub.Bind(_bindAddress);
					_connected = true;
				}

				_workerTask = Task.Factory.StartNew(
					() => PublishLoop(_cts.Token),
					_cts.Token,
					TaskCreationOptions.LongRunning,
					TaskScheduler.Default);

				EnsureMarketData();
				Log(string.Format("GC Tick Publisher ZMQ bound {0} topic={1}", _bindAddress, _topic), LogLevel.Information);
			}
			catch (Exception ex)
			{
				_connected = false;
				Log("GC Tick Publisher ZMQ start failed: " + ex.Message, LogLevel.Error);
			}
		}

		private void EnsureMarketData()
		{
			if (_marketHooked)
				return;

			_instrument = Instrument.GetInstrument(_instrumentName);
			if (_instrument == null)
			{
				Log(string.Format("Instrument '{0}' not found.", _instrumentName), LogLevel.Error);
				return;
			}

			_instrument.MarketData.Update += OnMarketDataUpdate;
			_marketHooked = true;
			Log("MarketData hooked: " + _instrument.FullName, LogLevel.Information);
		}

		private void StopEverything()
		{
			try
			{
				if (_uiTimer != null)
				{
					_uiTimer.Stop();
					_uiTimer = null;
				}

				if (_marketHooked && _instrument != null && _instrument.MarketData != null)
				{
					_instrument.MarketData.Update -= OnMarketDataUpdate;
					_marketHooked = false;
				}

				if (_cts != null)
				{
					_cts.Cancel();
					try
					{
						if (_workerTask != null)
							_workerTask.Wait(2000);
					}
					catch { }
					_cts.Dispose();
					_cts = null;
					_workerTask = null;
				}

				lock (_socketLock)
				{
					if (_pub != null)
					{
						try { _pub.Dispose(); } catch { }
						_pub = null;
					}
				}

				// Drain leftover queue
				TickData unused;
				while (_queue.TryDequeue(out unused)) { }

				_connected = false;
			}
			catch (Exception ex)
			{
				Log("GC Tick Publisher ZMQ stop: " + ex.Message, LogLevel.Warning);
			}
		}

		/// <summary>
		/// CRITICAL: only enqueue here — never do network I/O on the MD thread.
		/// </summary>
		private void OnMarketDataUpdate(object sender, MarketDataEventArgs e)
		{
			if (e == null)
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
			if (e.Volume <= 0)
				return;

			// Bound memory if Python is down / worker slow
			if (_queue.Count >= MaxQueueSize)
			{
				TickData dropped;
				if (_queue.TryDequeue(out dropped))
					Interlocked.Increment(ref _dropped);
			}

			TickData tick = new TickData
			{
				TimestampUtc = e.Time.ToUniversalTime(),
				Symbol = _instrumentName,
				Price = e.Price,
				Volume = e.Volume,
				Bid = _lastBid,
				Ask = _lastAsk
			};

			_queue.Enqueue(tick);
			Interlocked.Increment(ref _enqueued);
			_lastPrice = e.Price;
			_lastVolume = e.Volume;
		}

		private void PublishLoop(CancellationToken token)
		{
			while (!token.IsCancellationRequested)
			{
				TickData tick;
				if (!_queue.TryDequeue(out tick))
				{
					Thread.Sleep(1);
					continue;
				}

				try
				{
					string json = BuildJson(tick);
					lock (_socketLock)
					{
						if (_pub == null)
							continue;
						// multipart: topic + body (Python SUB filters on topic)
						_pub.SendMoreFrame(_topic).SendFrame(json);
					}
					Interlocked.Increment(ref _published);
					Interlocked.Increment(ref _publishedLastSecond);
					_connected = true;
				}
				catch (Exception)
				{
					// Fire-and-forget: never crash NT if subscriber is gone
					_connected = false;
					try { Thread.Sleep(5); } catch { }
				}
			}
		}

		private static string BuildJson(TickData t)
		{
			// Manual format (InvariantCulture) — avoids ambiguity / allocation of anonymous types
			return string.Format(CultureInfo.InvariantCulture,
				"{{\"timestamp\":\"{0:yyyy-MM-ddTHH:mm:ss.fff}Z\",\"symbol\":\"{1}\",\"price\":{2},\"volume\":{3},\"bid\":{4},\"ask\":{5}}}",
				t.TimestampUtc,
				t.Symbol,
				t.Price.ToString("F2", CultureInfo.InvariantCulture),
				t.Volume.ToString(CultureInfo.InvariantCulture),
				t.Bid.ToString("F2", CultureInfo.InvariantCulture),
				t.Ask.ToString("F2", CultureInfo.InvariantCulture));
		}

		// ---- UI ----
		private void ShowOrFocusWindow()
		{
			if (Application.Current == null)
				return;

			Application.Current.Dispatcher.InvokeAsync(() =>
			{
				if (_window != null)
				{
					_window.Show();
					_window.Activate();
					return;
				}

				_window = new NTWindow
				{
					Title = "GC Tick Publisher (ZeroMQ)",
					Width = 420,
					Height = 240,
					Content = BuildPanel()
				};
				_window.Closed += (s, e) => { _window = null; };
				_window.Show();

				_uiTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
				_uiTimer.Tick += (s, e) => RefreshUi();
				_uiTimer.Start();
			});
		}

		private UIElement BuildPanel()
		{
			var stack = new StackPanel { Margin = new Thickness(12) };
			_statusText = new TextBlock { FontSize = 16, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 0, 0, 8) };
			_tpsText = new TextBlock { FontSize = 13, Margin = new Thickness(0, 0, 0, 4) };
			_queueText = new TextBlock { FontSize = 13, Margin = new Thickness(0, 0, 0, 4) };
			_lastTickText = new TextBlock { FontSize = 13 };

			stack.Children.Add(new TextBlock
			{
				Text = "Menu: New → GC Tick Publisher ZMQ",
				FontSize = 11,
				Foreground = Brushes.Gray,
				Margin = new Thickness(0, 0, 0, 8)
			});
			stack.Children.Add(_statusText);
			stack.Children.Add(new TextBlock
			{
				Text = "PUB " + _bindAddress + "  topic=" + _topic,
				FontSize = 12,
				Foreground = Brushes.Gray
			});
			stack.Children.Add(new TextBlock
			{
				Text = "Instrument: " + _instrumentName + " (queue+worker, non-blocking)",
				FontSize = 12,
				Foreground = Brushes.Gray,
				Margin = new Thickness(0, 0, 0, 8)
			});
			stack.Children.Add(_tpsText);
			stack.Children.Add(_queueText);
			stack.Children.Add(_lastTickText);
			return stack;
		}

		private void RefreshUi()
		{
			long tps = Interlocked.Exchange(ref _publishedLastSecond, 0);
			if (_statusText == null)
				return;

			_statusText.Text = _connected ? "● CONNECTED (PUB)" : "● DISCONNECTED / waiting";
			_statusText.Foreground = _connected ? Brushes.LimeGreen : Brushes.OrangeRed;
			_tpsText.Text = string.Format(
				"Published/sec: {0}  |  Total pub: {1}  |  Enqueued: {2}",
				tps, Interlocked.Read(ref _published), Interlocked.Read(ref _enqueued));
			_queueText.Text = string.Format(
				"Queue: {0}  |  Dropped (backpressure): {1}",
				_queue.Count, Interlocked.Read(ref _dropped));
			_lastTickText.Text = string.Format(CultureInfo.InvariantCulture,
				"Last: {0:F2} x {1}  bid={2:F2} ask={3:F2}",
				_lastPrice, _lastVolume, _lastBid, _lastAsk);
		}
	}
}
