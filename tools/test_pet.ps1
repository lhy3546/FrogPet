# FrogPet acceptance test: click interaction / jumping / Ctrl+Alt+Q exit (ASCII only)
$ErrorActionPreference = "Stop"

Add-Type @'
using System;
using System.Runtime.InteropServices;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr lp);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lp);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, UIntPtr e);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct RECT { public int L, T, R, B; }
}
'@
[W]::SetProcessDPIAware() | Out-Null

function Find-PetHwnd([int]$targetPid) {
  $script:found = [IntPtr]::Zero
  $cb = [W+EnumProc]{
    param($h, $lp)
    $wpid = 0
    [W]::GetWindowThreadProcessId($h, [ref]$wpid) | Out-Null
    if ($wpid -eq $targetPid -and [W]::IsWindowVisible($h)) {
      $r = New-Object W+RECT
      [W]::GetWindowRect($h, [ref]$r) | Out-Null
      if (($r.R - $r.L) -gt 200 -and ($r.B - $r.T) -gt 200) { $script:found = $h; return $false }
    }
    return $true
  }
  [W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
  return $script:found
}

function Get-PetPid {
  $p = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'main\.py' } | Select-Object -First 1
  if ($p) { return [int]$p.ProcessId }
  $p2 = Get-Process FrogPet -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($p2) { return $p2.Id }
  return 0
}

function Click-At([int]$x, [int]$y) {
  [W]::SetCursorPos($x, $y) | Out-Null
  Start-Sleep -Milliseconds 150
  [W]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 60
  [W]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
}

function Drag-At([int]$x, [int]$y, [int]$dx, [int]$dy) {
  [W]::SetCursorPos($x, $y) | Out-Null
  Start-Sleep -Milliseconds 150
  [W]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 120
  for ($i = 1; $i -le 8; $i++) {
    [W]::SetCursorPos($x + [int]($dx * $i / 8), $y + [int]($dy * $i / 8)) | Out-Null
    Start-Sleep -Milliseconds 40
  }
  Start-Sleep -Milliseconds 120
  [W]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
}

Write-Output "== FrogPet acceptance test =="
$petPid = Get-PetPid
if ($petPid -eq 0) { Write-Output "FAIL: pet process not found"; exit 1 }
Write-Output "pet pid = $petPid"

$hwnd = Find-PetHwnd $petPid
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "FAIL: pet window not found"; exit 1 }
$r = New-Object W+RECT
[W]::GetWindowRect($hwnd, [ref]$r) | Out-Null
Write-Output ("rect before: {0},{1} - {2},{3}" -f $r.L, $r.T, $r.R, $r.B)

# click on frog body: center x, 45% height (body area; feet sit at 58%)
$cx = ($r.L + $r.R) / 2
$cx = [int][Math]::Round($cx)
$cy = [int][Math]::Round($r.T + ($r.B - $r.T) * 0.45)
Write-Output ("click at {0},{1}" -f $cx, $cy)
$log = Join-Path $env:LOCALAPPDATA "FrogPet\log.txt"
$delta = 0
for ($attempt = 1; $attempt -le 5; $attempt++) {
  $before = @(Get-Content $log -ErrorAction SilentlyContinue).Count
  Click-At $cx $cy
  Start-Sleep -Milliseconds 900
  $lines = @(Get-Content $log -ErrorAction SilentlyContinue)
  $headInteract = @($lines[0..([Math]::Min($before, $lines.Count) - 1)] | Select-String "interact:").Count
  $delta = @($lines | Select-String "interact:").Count - $headInteract
  if ($delta -ge 1) { break }
  # frog may have been mid-jump; re-aim at its current rect and retry
  [W]::GetWindowRect($hwnd, [ref]$r) | Out-Null
  $cx = [int][Math]::Round(($r.L + $r.R) / 2)
  $cy = [int][Math]::Round($r.T + ($r.B - $r.T) * 0.45)
  Start-Sleep -Milliseconds 800
}
Write-Output "new interact entries this click = $delta (attempts: $attempt)"
if ($delta -ge 1) { Write-Output "PASS: click -> interact" } else { Write-Output "FAIL: no interact" }

# screenshot right after click (bubble may be visible)
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$bmp = New-Object System.Drawing.Bitmap 900, 700
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($cx - 450, $cy - 400, 0, 0, (New-Object System.Drawing.Size(900, 700)))
$bmp.Save("D:\desk\FrogPet\shot_click.png")
$g.Dispose(); $bmp.Dispose()

# drag test: press on frog body, move right-down 200px, release; window must follow
Start-Sleep -Milliseconds 600
[W]::GetWindowRect($hwnd, [ref]$r) | Out-Null
$dx0 = $r.L; $dy0 = $r.T
$px = [int][Math]::Round(($r.L + $r.R) / 2)
$py = [int][Math]::Round($r.T + ($r.B - $r.T) * 0.45)
Write-Output "drag from $px,$py ..."
Drag-At $px $py 200 80
Start-Sleep -Milliseconds 250
# screenshot right after drop: splash droplets + pond should be visible
$bmp = New-Object System.Drawing.Bitmap 900, 780
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($px + 200 - 450, $py + 80 - 480, 0, 0, (New-Object System.Drawing.Size(900, 780)))
$bmp.Save("D:\desk\FrogPet\shot_drop.png")
$g.Dispose(); $bmp.Dispose()
Start-Sleep -Milliseconds 500
[W]::GetWindowRect($hwnd, [ref]$r) | Out-Null
$mdx = $r.L - $dx0; $mdy = $r.T - $dy0
Write-Output "window moved during drag: $mdx, $mdy"
if ([Math]::Abs($mdx) -gt 120 -and [Math]::Abs($mdy) -gt 40) { Write-Output "PASS: drag works" } else { Write-Output "FAIL: drag did not move window" }

# movement check: rect should change within 12s
$r0L = $r.L; $r0T = $r.T
Start-Sleep -Seconds 12
[W]::GetWindowRect($hwnd, [ref]$r) | Out-Null
Write-Output ("rect after 12s: {0},{1} - {2},{3}" -f $r.L, $r.T, $r.R, $r.B)
$dx = [Math]::Abs($r.L - $r0L) + [Math]::Abs($r.T - $r0T)
if ($dx -gt 30) { Write-Output "PASS: jumping works (moved $dx px)" } else { Write-Output "WARN: no move" }

# Ctrl+Alt+Q exit
Write-Output "sending Ctrl+Alt+Q ..."
$ws = New-Object -ComObject WScript.Shell
$ws.SendKeys("^%q")
Start-Sleep -Seconds 2
$alive = Get-Process -Id $petPid -ErrorAction SilentlyContinue
if ($alive) { Write-Output "FAIL: process still alive" } else { Write-Output "PASS: Ctrl+Alt+Q exited pet" }
