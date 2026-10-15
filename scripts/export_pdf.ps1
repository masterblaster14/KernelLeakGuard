# Export the generated Word/PowerPoint deliverables to PDF using Microsoft Office
# (Windows). Word also refreshes the table of contents and page numbers.
#   powershell -File scripts\export_pdf.ps1 -Docs "\\wsl.localhost\Ubuntu\home\<user>\KernelLeakGuard\docs"
param([Parameter(Mandatory = $true)][string]$Docs)

$tmp = Join-Path $env:TEMP "klg_export"
New-Item -ItemType Directory -Force $tmp | Out-Null

$word = New-Object -ComObject Word.Application
$word.Visible = $false
Get-ChildItem $Docs -Filter "KernelLeakGuard_*.docx" | ForEach-Object {
    $local = Join-Path $tmp $_.Name
    Copy-Item $_.FullName $local -Force
    $d = $word.Documents.Open($local)
    $d.Fields.Update() | Out-Null
    foreach ($toc in $d.TablesOfContents) { $toc.Update() }
    $d.Save()
    $pdf = [IO.Path]::ChangeExtension($local, ".pdf")
    $d.SaveAs2($pdf, 17)
    $pages = $d.ComputeStatistics(2)
    $d.Close()
    Copy-Item $local $_.FullName -Force          # keep the refreshed TOC in the .docx
    Copy-Item $pdf (Join-Path $Docs ([IO.Path]::GetFileName($pdf))) -Force
    "{0}: {1} pages" -f $_.Name, $pages
}
$word.Quit()

$ppt = New-Object -ComObject PowerPoint.Application
Get-ChildItem $Docs -Filter "KernelLeakGuard_*.pptx" | ForEach-Object {
    $local = Join-Path $tmp $_.Name
    Copy-Item $_.FullName $local -Force
    $p = $ppt.Presentations.Open($local, $true, $false, $false)
    $pdf = [IO.Path]::ChangeExtension($local, ".pdf")
    $p.SaveAs($pdf, 32)
    "{0}: {1} slides" -f $_.Name, $p.Slides.Count
    $p.Close()
    Copy-Item $pdf (Join-Path $Docs ([IO.Path]::GetFileName($pdf))) -Force
}
$ppt.Quit()
