# Generate deterministic OCR benchmark pages with Windows GDI+ text shaping.
# The source strings live in cases.json (UTF-8) so this script stays ASCII-only
# and Windows PowerShell 5.1 cannot corrupt the Burmese text.
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$fixtureDir = Join-Path $root '..\backend\tests\fixtures\ocr-synthetic'
$casesPath = Join-Path $fixtureDir 'cases.json'
$cases = [IO.File]::ReadAllText($casesPath, [Text.Encoding]::UTF8) | ConvertFrom-Json

foreach ($case in $cases) {
    $imagePath = Join-Path $fixtureDir $case.image
    $referencePath = Join-Path $fixtureDir $case.reference
    $imageDir = Split-Path -Parent $imagePath
    New-Item -ItemType Directory -Force -Path $imageDir | Out-Null

    $bitmap = [System.Drawing.Bitmap]::new(2480, 3508)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.Clear([System.Drawing.Color]::White)
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality

    $y = 320
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($line in $case.lines) {
        $font = [System.Drawing.Font]::new(
            $line.font,
            [single]$line.size,
            [System.Drawing.FontStyle]::Regular,
            [System.Drawing.GraphicsUnit]::Pixel
        )
        $graphics.DrawString($line.text, $font, [System.Drawing.Brushes]::Black, [single]180, [single]$y)
        $font.Dispose()
        $lines.Add($line.text)
        $y += [int]($line.size * 1.7)
    }

    $bitmap.Save($imagePath, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bitmap.Dispose()

    [IO.File]::WriteAllText(
        $referencePath,
        ($lines -join "`n"),
        [Text.UTF8Encoding]::new($false)
    )
    Write-Output "generated $($case.name)"
}
