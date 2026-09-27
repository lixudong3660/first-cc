# 启动番茄钟并把窗口截图存为 PNG，用于设计评审。
# 只截应用窗口自身的矩形，不抓整屏；退出时关闭该进程。
$ErrorActionPreference = "Stop"
$OutFile = "D:\PythonProject\first-cc\.claude\shot.png"

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinApi {
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int n);
}
"@

$proc = Start-Process -FilePath "python" `
    -ArgumentList "pomodoro.py" `
    -WorkingDirectory "D:\PythonProject\first-cc" `
    -PassThru -WindowStyle Normal

try {
    $h = [IntPtr]::Zero
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 250
        $proc.Refresh()
        if ($proc.MainWindowHandle -ne 0) { $h = $proc.MainWindowHandle; break }
    }
    if ($h -eq [IntPtr]::Zero) { Write-Output "NO_WINDOW"; exit 1 }

    [WinApi]::ShowWindow($h, 5) | Out-Null
    [WinApi]::SetForegroundWindow($h) | Out-Null
    Start-Sleep -Milliseconds 900

    $r = New-Object WinApi+RECT
    [WinApi]::GetWindowRect($h, [ref]$r) | Out-Null
    $w = [int]($r.Right - $r.Left)
    $ht = [int]($r.Bottom - $r.Top)
    Write-Output "RECT $($r.Left),$($r.Top) ${w}x${ht}"
    if ($w -le 0 -or $ht -le 0) { Write-Output "BAD_RECT"; exit 1 }

    $bmp = New-Object System.Drawing.Bitmap -ArgumentList $w, $ht
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $size = New-Object System.Drawing.Size -ArgumentList $w, $ht
    $g.CopyFromScreen($r.Left, $r.Top, 0, 0, $size)
    $bmp.Save($OutFile, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    Write-Output "SAVED $OutFile"
}
finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
}
