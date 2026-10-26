param([string]$Out = 'D:\bililive\autoshopkit\recon\resources\menu_cmds.txt')
$ErrorActionPreference='Stop'
Add-Type -Path 'C:\Users\yuche\AppData\Local\Temp\PeRes.cs'
$r = New-Object PeRes('D:\Inovance Control\AutoShop\AutoShop.exe'); $r.Parse()
$sb = New-Object System.Text.StringBuilder
$n = 0
foreach($m in ($r.leaves | Where-Object { $_.type -eq 4 })){
  $d = $m.data
  $menuid = $m.name
  $i = 0
  while ($i -lt $d.Length - 2) {
    $start = $i
    $s = ''
    while ($i + 1 -lt $d.Length) {
      $c = [char][BitConverter]::ToUInt16($d, $i)
      if (($c -ge [char]0x4e00 -and $c -le [char]0x9fff) -or ($c -ge [char]0x20 -and $c -le [char]0x7e) -or ($c -ge [char]0x3000 -and $c -le [char]0x303f) -or ($c -ge [char]0xff00 -and $c -le [char]0xffef)) {
        $s += $c; $i += 2
      } else { break }
    }
    if ($s.Length -ge 2) {
      $w = 0
      if ($start -ge 2) { $w = [BitConverter]::ToUInt16($d, $start - 2) }
      $text = $s
      # if the run's first char is exactly the preceding word, that word is the command id
      if ($w -ne 0 -and [int][char]$text[0] -eq $w) { $text = $text.Substring(1) }
      $flags = 0
      if ($start -ge 4) { $flags = [BitConverter]::ToUInt16($d, $start - 4) }
      [void]$sb.AppendLine(("{0}`t{1}`t{2}`t{3}" -f $menuid, $w, $flags, $text))
      $n++
    }
    $i += 2
  }
}
[System.IO.File]::WriteAllText($Out, $sb.ToString(), [System.Text.Encoding]::UTF8)
"wrote $Out entries=$n"
