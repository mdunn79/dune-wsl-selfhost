# Session window so Windows waits for battlegroup stop (WM_QUERYENDSESSION).
# Closing this window does not stop Funcom. Only a host shutdown/logoff does.
# Status is public /status.json (joinable, online count, map Ready). No names.
# Register At log on: Install-DuneScheduledMaintain.ps1 (task DuneBattlegroupWatch).
# Log: watch-dune-battlegroup.log

param(
    [switch]$Register
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$stopScript = Join-Path $here "Stop-DuneBattlegroup.ps1"
$logFile = Join-Path $here "watch-dune-battlegroup.log"
$taskName = "DuneBattlegroupWatch"

function Write-WatchLog([string]$Message) {
    $clean = ([string]$Message) -replace '\x1b\[[0-9;]*m', '' -replace "`r", "" -replace "`n", ""
    if ([string]::IsNullOrWhiteSpace($clean)) { return }
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $clean
    Add-Content -Path $logFile -Value $line
}

function Get-StatusUrl {
    $lan = ""
    $cfgPath = Join-Path $here "dune-install.config.ps1"
    if (Test-Path $cfgPath) {
        $cfg = Get-Content -Raw $cfgPath | Invoke-Expression
        if ($cfg.LanIp) { $lan = [string]$cfg.LanIp.Trim() }
    }
    if ([string]::IsNullOrWhiteSpace($lan)) {
        $raw = & wsl.exe -u dune -- cat /home/dune/.dune/lan-ip.conf 2>$null
        if ($raw) { $lan = ([string]$raw).Trim() }
    }
    if ([string]::IsNullOrWhiteSpace($lan)) { $lan = "127.0.0.1" }
    return "http://${lan}:18889/status.json"
}

if ($Register) {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $admin = [Security.Principal.WindowsPrincipal]::new($id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) {
        throw "Watch task register needs an elevated prompt."
    }
    if (-not (Test-Path $stopScript)) {
        throw "Missing $stopScript"
    }
    $ps = (Get-Command powershell.exe).Source
    $arg = "-STA -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`""
    $action = New-ScheduledTaskAction -Execute $ps -Argument $arg -WorkingDirectory $here
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null
    $task = Get-ScheduledTask -TaskName $taskName
    $task.Settings.DisallowStartIfOnBatteries = $false
    $task.Settings.StopIfGoingOnBatteries = $false
    $task.Settings.AllowHardTerminate = $true
    $task.Settings.StartWhenAvailable = $true
    $task.Settings.ExecutionTimeLimit = "PT0S"
    $task.Settings.Hidden = $false
    $task.Actions[0].WorkingDirectory = $here
    Set-ScheduledTask -InputObject $task | Out-Null
    Write-Host "Scheduled task $taskName installed (At log on for $($env:USERNAME))."
    Write-Host "  Window: this script (PowerShell host hidden). Close does not stop Funcom."
    Write-Host "  Log: $logFile"
    Write-Host "This did not start the window and did not stop maps."
    return
}

if (-not (Test-Path $stopScript)) {
    throw "Missing $stopScript"
}

if ([Threading.Thread]::CurrentThread.ApartmentState -ne "STA") {
    $ps = (Get-Command powershell.exe).Source
    Start-Process -FilePath $ps -WorkingDirectory $here -WindowStyle Hidden -ArgumentList @(
        "-STA", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
        "-File", $PSCommandPath
    )
    return
}

$created = $false
$mutex = New-Object System.Threading.Mutex($true, "Local\DuneBattlegroupWatch", [ref]$created)
if (-not $created) {
    $mutex.Dispose()
    Write-Host "Dune battlegroup watch is already running in this session."
    return
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Web.Extensions

$code = @'
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

public class DuneBattlegroupWatchForm : Form {
    const int WM_QUERYENDSESSION = 0x0011;
    const long ENDSESSION_CRITICAL = 0x40000000L;
    const int SW_HIDE = 0;
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern bool ShutdownBlockReasonCreate(IntPtr hWnd, string reason);
    [DllImport("user32.dll")]
    static extern bool ShutdownBlockReasonDestroy(IntPtr hWnd);
    [DllImport("kernel32.dll")]
    static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")]
    static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    readonly string stopScript;
    readonly string logFile;
    readonly string statusUrl;
    readonly Label hdr;
    readonly TextBox box;
    System.Windows.Forms.Timer poll;
    string lastKey = "";
    int stopping;

    public DuneBattlegroupWatchForm(string stopScript, string logFile, string statusUrl) {
        this.stopScript = stopScript;
        this.logFile = logFile;
        this.statusUrl = statusUrl;
        Text = "Dune battlegroup";
        Width = 720;
        Height = 420;
        MinimumSize = new Size(520, 280);
        StartPosition = FormStartPosition.CenterScreen;
        hdr = new Label();
        hdr.Dock = DockStyle.Top;
        hdr.Height = 118;
        hdr.Font = new Font("Consolas", 10f);
        hdr.Padding = new Padding(8, 8, 8, 4);
        hdr.Text = "Waiting for /status.json ...";
        box = new TextBox();
        box.Multiline = true;
        box.ReadOnly = true;
        box.ScrollBars = ScrollBars.Vertical;
        box.Dock = DockStyle.Fill;
        box.Font = new Font("Consolas", 9f);
        box.BorderStyle = BorderStyle.None;
        Controls.Add(box);
        Controls.Add(hdr);
        FormClosing += OnFormClosing;
        Shown += OnShown;
    }

    void OnShown(object sender, EventArgs e) {
        IntPtr con = GetConsoleWindow();
        if (con != IntPtr.Zero) ShowWindow(con, SW_HIDE);
        Append("Watching this Windows session. Close does not stop Funcom.");
        PollOnce();
        poll = new System.Windows.Forms.Timer();
        poll.Interval = 15000;
        poll.Tick += delegate { PollOnce(); };
        poll.Start();
    }

    void OnFormClosing(object sender, FormClosingEventArgs e) {
        if (poll != null) {
            poll.Stop();
            poll.Dispose();
            poll = null;
        }
        if (stopping != 0) return;
        Append("Window closed. Windows will not wait for battlegroup stop until this watch starts again.");
    }

    public void Append(string msg) {
        string line = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + msg;
        try { File.AppendAllText(logFile, line + Environment.NewLine); } catch {}
        if (box.IsDisposed) return;
        if (box.InvokeRequired) {
            try { BeginInvoke(new Action<string>(Append), msg); } catch {}
            return;
        }
        box.AppendText(line + Environment.NewLine);
    }

    static string Str(Dictionary<string, object> d, string key) {
        object v;
        if (d == null || !d.TryGetValue(key, out v) || v == null) return "";
        return Convert.ToString(v);
    }

    static bool Flag(Dictionary<string, object> d, string key) {
        object v;
        if (d == null || !d.TryGetValue(key, out v) || v == null) return false;
        if (v is bool) return (bool)v;
        string s = Convert.ToString(v);
        return s == "True" || s == "true" || s == "1";
    }

    static int Num(Dictionary<string, object> d, string key) {
        object v;
        if (d == null || !d.TryGetValue(key, out v) || v == null) return 0;
        try { return Convert.ToInt32(v); } catch { return 0; }
    }

    void PollOnce() {
        if (stopping != 0) return;
        ThreadPool.QueueUserWorkItem(delegate {
            string header;
            string key;
            string logLine;
            string title;
            try {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(statusUrl);
                req.Timeout = 5000;
                req.ReadWriteTimeout = 5000;
                req.Proxy = null;
                string json;
                using (WebResponse resp = req.GetResponse())
                using (StreamReader sr = new StreamReader(resp.GetResponseStream()))
                    json = sr.ReadToEnd();
                JavaScriptSerializer ser = new JavaScriptSerializer();
                Dictionary<string, object> d = ser.DeserializeObject(json) as Dictionary<string, object>;
                if (d == null) throw new Exception("not an object");
                if (Flag(d, "ok") == false && !string.IsNullOrEmpty(Str(d, "error")))
                    throw new Exception(Str(d, "error"));
                string name = Str(d, "title");
                bool joinable = Flag(d, "joinable");
                int online = Num(d, "online");
                bool modifying = Flag(d, "modifying");
                bool updating = Flag(d, "updating");
                StringBuilder mapsHdr = new StringBuilder();
                StringBuilder mapsKey = new StringBuilder();
                StringBuilder mapsLog = new StringBuilder();
                object mapsObj;
                IEnumerable mapsEnum = null;
                if (d.TryGetValue("maps", out mapsObj) && mapsObj is IEnumerable && !(mapsObj is string))
                    mapsEnum = (IEnumerable)mapsObj;
                if (mapsEnum != null) {
                    foreach (object item in mapsEnum) {
                        Dictionary<string, object> m = item as Dictionary<string, object>;
                        string kind = Str(m, "kind");
                        string phase = Str(m, "phase");
                        bool ready = Flag(m, "ready");
                        string one = kind + "  " + phase + "  " + (ready ? "ready" : "not-ready");
                        if (mapsHdr.Length > 0) mapsHdr.AppendLine();
                        mapsHdr.Append(one);
                        if (mapsLog.Length > 0) mapsLog.Append("; ");
                        mapsLog.Append(one.Replace("  ", " "));
                        mapsKey.Append(kind).Append(":").Append(phase).Append(":").Append(ready ? "1" : "0").Append("|");
                    }
                }
                string joinWord = joinable ? "JOINABLE" : "NOT JOINABLE";
                StringBuilder hb = new StringBuilder();
                hb.AppendLine(string.IsNullOrEmpty(name) ? "Dune" : name);
                hb.Append(joinWord).Append("    online ").Append(online);
                if (mapsHdr.Length > 0) { hb.AppendLine(); hb.Append(mapsHdr.ToString()); }
                if (modifying) { hb.AppendLine(); hb.Append("Gateway Modifying"); }
                if (updating) { hb.AppendLine(); hb.Append("Steam/maintain running"); }
                header = hb.ToString();
                key = joinWord + "|" + online + "|" + mapsKey + (modifying ? "1" : "0") + "|" + (updating ? "1" : "0");
                logLine = joinWord + " online=" + online;
                if (mapsLog.Length > 0) logLine += "  " + mapsLog;
                if (modifying) logLine += "  Gateway Modifying";
                if (updating) logLine += "  Steam/maintain";
                title = "Dune battlegroup — " + joinWord;
            } catch (Exception ex) {
                header = "admin /status.json unreachable" + Environment.NewLine + ex.Message;
                key = "down";
                logLine = "status.json failed";
                title = "Dune battlegroup — admin down";
            }
            try {
                BeginInvoke(new Action(delegate {
                    if (hdr.IsDisposed) return;
                    Text = title;
                    hdr.Text = header;
                    if (key != lastKey) {
                        lastKey = key;
                        Append(logLine);
                    }
                }));
            } catch {}
        });
    }

    void BeginStop() {
        if (Interlocked.Exchange(ref stopping, 1) != 0) return;
        if (poll != null) { poll.Stop(); }
        Append("Windows shutdown: battlegroup stop...");
        ThreadPool.QueueUserWorkItem(delegate {
            try {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "powershell.exe";
                psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + stopScript + "\"";
                psi.WorkingDirectory = Path.GetDirectoryName(stopScript);
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                Process p = Process.Start(psi);
                if (p != null) p.WaitForExit(180000);
                Append("battlegroup stop finished.");
            } catch (Exception ex) {
                Append("battlegroup stop failed: " + ex.Message);
            }
            try {
                BeginInvoke(new Action(delegate {
                    try { ShutdownBlockReasonDestroy(this.Handle); } catch {}
                    Close();
                }));
            } catch {}
        });
    }

    protected override void WndProc(ref Message m) {
        if (m.Msg == WM_QUERYENDSESSION) {
            BeginStop();
            bool critical = (m.LParam.ToInt64() & ENDSESSION_CRITICAL) != 0;
            if (!critical) {
                ShutdownBlockReasonCreate(this.Handle, "Stopping Funcom maps");
                m.Result = IntPtr.Zero;
                return;
            }
            Append("Critical shutdown: cannot block Windows.");
        }
        base.WndProc(ref m);
    }
}
'@

try {
    Add-Type -TypeDefinition $code -ReferencedAssemblies @(
        "System.dll",
        "System.Core.dll",
        "System.Drawing.dll",
        "System.Windows.Forms.dll",
        "System.Web.Extensions.dll"
    )
} catch {
    if ("$($_.Exception.Message)" -notmatch "already exists") { throw }
}

$statusUrl = Get-StatusUrl
Write-WatchLog "watch started (pid $PID) $statusUrl"
[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object DuneBattlegroupWatchForm $stopScript, $logFile, $statusUrl
try {
    [System.Windows.Forms.Application]::Run($form)
} finally {
    Write-WatchLog "watch exited (pid $PID)"
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
