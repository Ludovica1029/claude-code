# Install the Claude Agent SDK (Python) into a folder on the Windows desktop.
# Usage (PowerShell):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\install-windows.ps1
$ErrorActionPreference = "Stop"

$Desktop = [Environment]::GetFolderPath("Desktop")
$Target  = Join-Path $Desktop "claude-agent-sdk"

Write-Host "==> 安装目录: $Target"

# 1. Python >= 3.10
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { $Python = "py"; $PyArgs = @("-3") } else { $Python = "python"; $PyArgs = @() }
try {
    $ver = & $Python @PyArgs -c "import sys;print('%d.%d'%sys.version_info[:2])"
} catch {
    Write-Error "未找到 Python。请先从 https://www.python.org/downloads/ 安装 Python 3.10+（勾选 Add to PATH）。"
}
if ([version]$ver -lt [version]"3.10") {
    Write-Error "需要 Python 3.10+，当前为 $ver"
}
Write-Host "==> Python $ver"

# 2. Create folder + virtualenv
New-Item -ItemType Directory -Force -Path $Target | Out-Null
& $Python @PyArgs -m venv (Join-Path $Target ".venv")
$VenvPy = Join-Path $Target ".venv\Scripts\python.exe"

# 3. Install the SDK
& $VenvPy -m pip install --upgrade pip
& $VenvPy -m pip install --upgrade claude-agent-sdk

# 4. Windows wheels do not bundle Claude Code; install the native claude.exe
#    (the SDK refuses npm's claude.cmd shim on Windows).
$ClaudeExe = Join-Path $HOME ".local\bin\claude.exe"
if (-not (Test-Path $ClaudeExe) -and -not (Get-Command claude.exe -ErrorAction SilentlyContinue)) {
    Write-Host "==> 安装 Claude Code (claude.exe)"
    Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
}

# 5. Copy example + launcher
Copy-Item -Force (Join-Path $PSScriptRoot "hello_agent.py") $Target
@"
@echo off
cd /d "%~dp0"
if "%ANTHROPIC_API_KEY%"=="" set /p ANTHROPIC_API_KEY=请输入 ANTHROPIC_API_KEY: 
".venv\Scripts\python.exe" hello_agent.py %*
pause
"@ | Set-Content -Encoding Default (Join-Path $Target "run-agent.bat")

& $VenvPy -c "import claude_agent_sdk; print('claude-agent-sdk', claude_agent_sdk.__version__, '安装成功')"
Write-Host ""
Write-Host "完成！双击桌面上 claude-agent-sdk\run-agent.bat 即可运行示例。"
Write-Host "建议永久设置 API Key: setx ANTHROPIC_API_KEY `"sk-ant-...`""
