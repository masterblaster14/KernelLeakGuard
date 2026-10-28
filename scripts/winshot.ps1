# Screenshot a web page with a normal (not headless) Edge window placed off-screen,
# rendered with PrintWindow. Used by scripts/capture_screenshots.py for the dashboard,
# whose frontend does not run in headless Edge.
param([string]$Url, [string]$Out, [int]$W = 1500, [int]$H = 950, [int]$Wait = 15, [double]$Scale = 1.0)
Add-Type @"
using System; using System.Collections.Generic; using System.Runtime.InteropServices; using System.Text;
public class PW { public delegate bool P(IntPtr h, IntPtr l);
 [DllImport("user32.dll")] public static extern bool EnumWindows(P p, IntPtr l);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out R r);
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
 [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
 public struct R { public int L,T,Ri,B; }
 public static IntPtr Find(HashSet<uint> pids) { IntPtr f = IntPtr.Zero; long best = 0;
   EnumWindows((h,l) => { uint pid; GetWindowThreadProcessId(h, out pid);
     if (pids.Contains(pid) && IsWindowVisible(h) && GetWindowTextLength(h) > 0) {
       R r; GetWindowRect(h, out r); long a = (long)(r.Ri - r.L) * (r.B - r.T);
       if (a > best) { best = a; f = h; } }
     return true; }, IntPtr.Zero); return f; } }
"@
Add-Type -AssemblyName System.Drawing
$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$prof = Join-Path $env:TEMP "klg_edge_profile"
$args = @("--user-data-dir=$prof", "--no-first-run", "--no-default-browser-check", "--app=$Url",
          "--window-position=-4200,0", "--window-size=$W,$H", "--force-device-scale-factor=$Scale",
          "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
          "--disable-background-timer-throttling")
Start-Process -FilePath $edge -ArgumentList $args | Out-Null
Start-Sleep -Seconds $Wait
$pids = New-Object 'System.Collections.Generic.HashSet[uint32]'
Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object { $_.CommandLine -like "*klg_edge_profile*" } | ForEach-Object { [void]$pids.Add([uint32]$_.ProcessId) }
$h = [PW]::Find($pids)
if ($h -eq [IntPtr]::Zero) { "no window" } else {
  $r = New-Object PW+R; [PW]::GetWindowRect($h, [ref]$r) | Out-Null
  $b = New-Object Drawing.Bitmap ($r.Ri - $r.L), ($r.B - $r.T)
  $g = [Drawing.Graphics]::FromImage($b); $dc = $g.GetHdc()
  [PW]::PrintWindow($h, $dc, 2) | Out-Null; $g.ReleaseHdc($dc); $b.Save($Out); "saved " + $b.Width + "x" + $b.Height }
$pids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
