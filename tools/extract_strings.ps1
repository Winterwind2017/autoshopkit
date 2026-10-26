param(
  [Parameter(Mandatory=$true)][string]$Path,
  [Parameter(Mandatory=$true)][string]$Out,
  [int]$MinAscii = 5,
  [int]$MinUnicode = 4
)
$ErrorActionPreference = 'Stop'
$bytes = [System.IO.File]::ReadAllBytes($Path)
$ascii = [System.Text.Encoding]::Latin1.GetString($bytes)
$sb = New-Object System.Text.StringBuilder
$rxAscii = New-Object System.Text.RegularExpressions.Regex ("[\x20-\x7E\t]{" + $MinAscii + ",}")
foreach ($m in $rxAscii.Matches($ascii)) { [void]$sb.Append('A|').Append($m.Value).Append("`n") }
$uni = [System.Text.Encoding]::Unicode.GetString($bytes)
$rxUni = New-Object System.Text.RegularExpressions.Regex ("[\x20-\x7E\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]{" + $MinUnicode + ",}")
foreach ($m in $rxUni.Matches($uni)) { [void]$sb.Append('U|').Append($m.Value).Append("`n") }
[System.IO.File]::WriteAllText($Out, $sb.ToString(), [System.Text.Encoding]::UTF8)
"$Path -> $Out : $($rxAscii.Matches($ascii).Count) ascii, $($rxUni.Matches($uni).Count) unicode"
