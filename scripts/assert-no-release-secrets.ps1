param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Path)) {
    throw "Scan path does not exist: $Path"
}

$root = Resolve-Path -LiteralPath $Path
$envFiles = Get-ChildItem -LiteralPath $root -Force -Recurse -File -Filter ".env"
if ($envFiles) {
    Write-Error ("KEY-LEAK GUARD failed: bundled .env file(s): " + (($envFiles.FullName | ForEach-Object { $_ -replace [regex]::Escape((Get-Location).Path + [IO.Path]::DirectorySeparatorChar), "" }) -join ", "))
    exit 1
}

$secretPatterns = @(
    '(?i)(ANTHROPIC_API_KEY|OPENAI_API_KEY|FMP_API_KEY|XAI_API_KEY|GROQ_API_KEY)\s*[:=]\s*["'']?[A-Za-z0-9_./+=:-]{20,}',
    '(?i)\bsk-ant-[A-Za-z0-9_-]{16,}',
    '(?i)\bsk-[A-Za-z0-9_-]{20,}',
    '(?i)\bxai-[A-Za-z0-9_-]{16,}',
    '(?i)\bgsk_[A-Za-z0-9_-]{16,}'
)

function Mask-SecretMatch {
    param([string]$Value)

    if ($Value -match '([:=]\s*["'']?)(.{4}).*$') {
        return ($Value -replace '([:=]\s*["'']?)(.{4}).*$', '$1$2***')
    }

    if ($Value.Length -le 8) {
        return "***"
    }

    return $Value.Substring(0, 6) + "***"
}

$files = Get-ChildItem -LiteralPath $root -Force -Recurse -File

$findings = New-Object System.Collections.Generic.List[string]
foreach ($file in $files) {
    foreach ($pattern in $secretPatterns) {
        $matches = Select-String -LiteralPath $file.FullName -Pattern $pattern -AllMatches -ErrorAction SilentlyContinue
        foreach ($match in $matches) {
            foreach ($capture in $match.Matches) {
                $masked = Mask-SecretMatch -Value $capture.Value
                $relative = Resolve-Path -LiteralPath $file.FullName -Relative
                $findings.Add("${relative}:$($match.LineNumber): $masked")
            }
        }
    }
}

if ($findings.Count -gt 0) {
    Write-Error ("KEY-LEAK GUARD failed; secret-looking content found:`n" + ($findings -join "`n"))
    exit 1
}

Write-Host "KEY-LEAK GUARD passed for $root"
