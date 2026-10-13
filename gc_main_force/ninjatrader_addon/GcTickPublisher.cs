// ------------------------------------------------------------
// GcTickPublisher.cs — NinjaTrader 8 Add-On
// Menu: Control Center → New → Add-Ons → GC Tick Publisher
// Publishes GC ticks as JSON lines over TCP port 5556 (no NetMQ).
// ------------------------------------------------------------
#region Using declarations
using System;
using System.Collections.Concurrent;
using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Text;
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
#endregion

namespace NinjaTrader.NinjaScript.AddOns
{
	public class GcTickPublisher : AddOnBase
	{
		private NTMenuItem _menuItem;
		private NTMenuItem _newMenu;

		private TcpListener _listener;
		private readonly ConcurrentDictionary<int, TcpClient> _clients = new ConcurrentDictionary<int, TcpClient>();
		private int _clientSeq;
		private CancellationTokenSource _cts;
		private Instrument _instrument;
		private NTWindow _window;
		private TextBlock _statusText;
		private TextBlock _tpsText;
		private TextBlock _lastTickText;
		private TextBlock _clientsText;
		private DispatcherTimer _uiTimer;

		private long _ticksPublished;
		private long _ticksLastSecond;
		private double _lastPrice;
		private long _lastVolume;
		private bool _listening;
		private bool _marketHooked;
		private readonly int _port = 5556;
		private readonly string _instrumentName = "GC";
		private readonly object _startLock = new object();

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "Publishes GC ticks over TCP for Main Force Flow (Python). Open via New → Add-Ons → GC Tick Publisher.";
				Name = "GC Tick Publisher";
			}
			else if (State == State.Terminated)
			{
				StopPublisher();
			}
		}

		// Inject menu into Control Center: New → Add-Ons → GC Tick Publisher
		protected override void OnWindowCreated(Window window)
		{
			ControlCenter cc = window as ControlCenter;
			if (cc == null)
				return;

			_newMenu = cc.FindFirst("ControlCenterMenuItemNew") as NTMenuItem;
			if (_newMenu == null)
				return;

			// Avoid duplicate menu entries if Control Center recreates
			foreach (object item in _newMenu.Items)
			{
				NTMenuItem mi = item as NTMenuItem;
				if (mi != null && mi.Header != null && mi.Header.ToString() == "GC Tick Publisher")
					return;
			}

			_menuItem = new NTMenuItem
			{
				Header = "GC Tick Publisher",
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
			EnsurePublisherStarted();
			ShowOrFocusWindow();
		}

		private void EnsurePublisherStarted()
		{
			lock (_startLock)
			{
				if (_listening)
				{
					EnsureMarketData();
					return;
				}

				try
				{
					_cts = new CancellationTokenSource();
					_listener = new TcpListener(IPAddress.Any, _port);
					_listener.Start();
					_listening = true;
					Task.Run(() => AcceptLoop(_cts.Token));
					EnsureMarketData();
					Log(string.Format("GC Tick Publisher listening on TCP:{0}", _port), LogLevel.Information);
				}
				catch (Exception ex)
				{
					_listening = false;
					Log("GC Tick Publisher failed to start: " + ex.Message, LogLevel.Error);
				}
			}
		}

		private void EnsureMarketData()
		{
			if (_marketHooked)
				return;

			_instrument = Instrument.GetInstrument(_instrumentName);
			if (_instrument == null)
			{
				Log(string.Format("Instrument '{0}' not found. Open a GC chart / check symbol.", _instrumentName), LogLevel.Error);
				return;
			}

			_instrument.MarketData.Update += OnMarketDataUpdate;
			_marketHooked = true;
			Log("Subscribed to market data: " + _instrument.FullName, LogLevel.Information);
		}

		private void StopPublisher()
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
				_listening = false;
			}
			catch (Exception ex)
			{
				Log("GC Tick Publisher stop error: " + ex.Message, LogLevel.Warning);
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
					Log("Python client connected #" + id, LogLevel.Information);
				}
				catch (ObjectDisposedException)
				{
					break;
				}
				catch (Exception)
				{
					if (token.IsCancellationRequested)
						break;
					try { await Task.Delay(250, token).ConfigureAwait(false); } catch { break; }
				}
			}
		}

		private void OnMarketDataUpdate(object sender, MarketDataEventArgs e)
		{
			if (e.MarketDataType != MarketDataType.Last)
				return;

			double price = e.Price;
			long volume = e.Volume;
			if (volume <= 0)
				return;

			double bid = 0;
			double ask = 0;
			try
			{
				if (_instrument != null && _instrument.MarketData != null)
				{
					if (_instrument.MarketData.Bid != null)
						bid = _instrument.MarketData.Bid.Price;
					if (_instrument.MarketData.Ask != null)
						ask = _instrument.MarketData.Ask.Price;
				}
			}
			catch { }

			DateTime utc = e.Time.ToUniversalTime();
			string json = string.Format(CultureInfo.InvariantCulture,
				"{{\"timestamp\":\"{0:yyyy-MM-ddTHH:mm:ss.fff}Z\",\"symbol\":\"GC\",\"price\":{1:F2},\"volume\":{2},\"bid\":{3:F2},\"ask\":{4:F2}}}\n",
				utc, price, volume, bid, ask);

			Broadcast(Encoding.UTF8.GetBytes(json));
			Interlocked.Increment(ref _ticksPublished);
			Interlocked.Increment(ref _ticksLastSecond);
			_lastPrice = price;
			_lastVolume = volume;
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
					Title = "GC Tick Publisher (TCP)",
					Width = 400,
					Height = 230,
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
			_clientsText = new TextBlock { FontSize = 13, Margin = new Thickness(0, 0, 0, 4) };
			_lastTickText = new TextBlock { FontSize = 13 };

			stack.Children.Add(new TextBlock
			{
				Text = "Abra pelo menu: New → Add-Ons → GC Tick Publisher",
				FontSize = 11,
				Foreground = Brushes.Gray,
				Margin = new Thickness(0, 0, 0, 8)
			});
			stack.Children.Add(_statusText);
			stack.Children.Add(new TextBlock { Text = "TCP port: " + _port + "  (JSON lines)", FontSize = 12, Foreground = Brushes.Gray });
			stack.Children.Add(new TextBlock { Text = "Instrument: " + _instrumentName + " (100 oz)", FontSize = 12, Foreground = Brushes.Gray, Margin = new Thickness(0, 0, 0, 8) });
			stack.Children.Add(_tpsText);
			stack.Children.Add(_clientsText);
			stack.Children.Add(_lastTickText);
			return stack;
		}

		private void RefreshUi()
		{
			long tps = Interlocked.Exchange(ref _ticksLastSecond, 0);
			if (_statusText == null)
				return;

			_statusText.Text = _listening ? "● LISTENING" : "● STOPPED";
			_statusText.Foreground = _listening ? Brushes.LimeGreen : Brushes.OrangeRed;
			_tpsText.Text = string.Format("Ticks/sec: {0}  |  Total: {1}", tps, Interlocked.Read(ref _ticksPublished));
			_clientsText.Text = string.Format("Python clients: {0}", _clients.Count);
			_lastTickText.Text = string.Format(CultureInfo.InvariantCulture, "Last: {0:F2}  x {1}", _lastPrice, _lastVolume);
		}
	}
}
