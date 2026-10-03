<#
.SYNOPSIS
  local-ai-lab - get the course onto this machine and ready to run. Windows (PowerShell 5.1 or 7).

.DESCRIPTION
  One line, from a PowerShell prompt:

    irm https://raw.githubusercontent.com/nikolareljin/local-ai-lab/main/setup.ps1 | iex

  with options (iex cannot pass any):

    & ([scriptblock]::Create((irm https://raw.githubusercontent.com/nikolareljin/local-ai-lab/main/setup.ps1))) -Models all

  or, to read it first (recommended for any script from the internet):

    irm https://raw.githubusercontent.com/nikolareljin/local-ai-lab/main/setup.ps1 -OutFile setup.ps1
    notepad setup.ps1
    powershell -ExecutionPolicy Bypass -File .\setup.ps1

  What it does, in order:
    1. checks the tools the course needs and says how to get the missing ones
    2. clones the repository (skipped when run inside a clone)
    3. creates the Python virtualenv and installs requirements.txt into it
    4. pulls the local model the lessons use, if Ollama is installed
    5. prints what is ready and what to run next

  What it never does: download and run another installer by itself. With
  -WithSystemPackages it asks winget (Microsoft's signed package source) for Git, Python
  and Ollama, and nothing else.

  The lessons are started with the `run` script, which is Bash: use Git Bash (it comes with
  Git for Windows) or WSL for `./run -l 10 demo`.

.PARAMETER Dir
  Where to clone. Default: .\local-ai-lab
.PARAMETER Ref
  A release tag to check out instead of main.
.PARAMETER WithSystemPackages
  Install Git, Python and Ollama with winget when they are missing.
.PARAMETER Models
  Ollama models to pull: none, small (qwen3:1.7b, the default) or all (adds qwen3.5:4b).
.PARAMETER DryRun
  Print what would be done, do nothing.
#>
[CmdletBinding()]
param(
  [string]$Dir = "local-ai-lab",
  [string]$Ref = "",
  [switch]$WithSystemPackages,
  [ValidateSet("none", "small", "all")][string]$Models = "small",
  [switch]$DryRun
)

# Everything runs in a child scope: when the script is piped into iex it shares the caller's
# session, and must not leave functions or a changed $ErrorActionPreference behind, or close
# the window (so: throw and return, never exit).
& {
  $ErrorActionPreference = "Stop"
  $RepoUrl = if ($env:LOCAL_AI_LAB_REPO) { $env:LOCAL_AI_LAB_REPO } else { "https://github.com/nikolareljin/local-ai-lab.git" }
  $SmallModel = "qwen3:1.7b"   # the simulated Jev and the LLM arm of Lesson 10; tools in Lesson 9
  $BigModel = "qwen3.5:4b"     # optional: the better, slower simulated Jev

  function Info($text) { Write-Host "[setup] $text" }
  function Have($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

  # Run a native command for its exit code or output only. Windows PowerShell 5.1 turns anything
  # a program writes to stderr into a terminating error under "Stop", so relax it for the call.
  function Invoke-Quiet {
    param([string]$Exe, [string[]]$Arguments)
    $ErrorActionPreference = "Continue"
    & $Exe @Arguments 2>$null
  }

  # Run a command, or only print it under -DryRun. Stops the script when the command fails.
  function Invoke-Step {
    param([string]$Exe, [string[]]$Arguments)
    if ($DryRun) { Write-Host "  would run: $Exe $($Arguments -join ' ')"; return }
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe $($Arguments -join ' ') failed with exit code $LASTEXITCODE" }
  }

  # The Python to build the virtualenv with: `py -3` (the Windows launcher), `python` or `python3`, 3.10+.
  function Find-Python {
    foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
      $exe = $candidate[0]
      if (-not (Have $exe)) { continue }
      $extra = @($candidate | Select-Object -Skip 1)
      Invoke-Quiet $exe ($extra + @("-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)")) | Out-Null
      if ($LASTEXITCODE -eq 0) { return , $candidate }
    }
    return $null
  }

  # ----------------------------------------------------------------------------- 1. tools
  $python = Find-Python
  if (-not (Have "git") -or -not $python) {
    if ($WithSystemPackages) {
      if (-not (Have "winget")) { throw "winget is not available; install Git and Python 3.10+ by hand" }
      Info "installing Git and Python with winget"
      if (-not (Have "git")) { Invoke-Step "winget" @("install", "--id", "Git.Git", "-e", "--source", "winget") }
      if (-not $python) { Invoke-Step "winget" @("install", "--id", "Python.Python.3.12", "-e", "--source", "winget") }
      if (-not $DryRun) {
        Write-Host "Git or Python was just installed. Open a new PowerShell window so they are on PATH, then run this script again."
        return
      }
    }
    else {
      if (-not (Have "git")) { Write-Warning "Git is missing." }
      if (-not $python) { Write-Warning "Python 3.10 or newer is missing." }
      Write-Host "Install them, or run again with -WithSystemPackages:"
      Write-Host "  winget install --id Git.Git -e --source winget"
      Write-Host "  winget install --id Python.Python.3.12 -e --source winget"
      if (-not $DryRun) { Write-Warning "Nothing was changed."; return }
    }
  }
  if (-not $python) { $python = @("python") }

  # ----------------------------------------------------------------------------- 2. the repository
  $inside = $null
  if (Have "git") { $inside = Invoke-Quiet "git" @("rev-parse", "--show-toplevel") }
  if ($inside -and (Test-Path (Join-Path $inside "run")) -and (Test-Path (Join-Path $inside "lessons"))) {
    $Root = (Resolve-Path $inside).Path
    Info "using the clone at $Root"
  }
  elseif (Test-Path (Join-Path $Dir ".git")) {
    $Root = (Resolve-Path $Dir).Path
    Info "using the existing clone at $Root"
  }
  else {
    Info "cloning $RepoUrl into $Dir"
    Invoke-Step "git" @("clone", "--recurse-submodules", $RepoUrl, $Dir)
    $Root = if (Test-Path $Dir) { (Resolve-Path $Dir).Path } else { $Dir }
  }
  if ($Ref) {
    Info "checking out $Ref"
    Invoke-Step "git" @("-C", $Root, "checkout", "--quiet", $Ref)
  }
  # The run script reads helper functions from a submodule; make sure it is there.
  Invoke-Step "git" @("-C", $Root, "submodule", "update", "--init", "--recursive", "--quiet")

  # ----------------------------------------------------------------------------- 3. Python environment
  # PowerShell 7 also runs on Linux and macOS, where a virtualenv keeps python in bin/.
  $onWindows = ($PSVersionTable.PSVersion.Major -lt 6) -or $IsWindows
  $venvPython = if ($onWindows) { Join-Path $Root "venv\Scripts\python.exe" } else { Join-Path $Root "venv/bin/python" }
  if (-not (Test-Path $venvPython)) {
    Info "creating the virtualenv at $(Join-Path $Root "venv")"
    $pyArgs = @($python | Select-Object -Skip 1) + @("-m", "venv", (Join-Path $Root "venv"))
    Invoke-Step $python[0] $pyArgs
  }
  Info "installing the course's Python packages into the virtualenv"
  Invoke-Step $venvPython @("-m", "pip", "install", "--quiet", "--upgrade", "pip")
  Invoke-Step $venvPython @("-m", "pip", "install", "--quiet", "-r", (Join-Path $Root "requirements.txt"))

  # ----------------------------------------------------------------------------- 4. local models
  # Why a model at all: Lesson 10's "simulated Jev" and its LLM arm are a small local model
  # answering through Ollama, and Lesson 9's tool calls use the same one. The demos replay
  # recordings and need no model; the live commands do.
  $ollamaNote = ""
  $modelReady = $false
  if ($Models -eq "none") {
    $ollamaNote = "skipped (-Models none)"
  }
  else {
    if (-not (Have "ollama") -and $WithSystemPackages -and (Have "winget")) {
      Info "installing Ollama with winget"
      Invoke-Step "winget" @("install", "--id", "Ollama.Ollama", "-e", "--source", "winget")
    }
    if (-not (Have "ollama")) {
      $ollamaNote = "Ollama is not installed: get it from https://ollama.com/download, then: ollama pull $SmallModel"
    }
    else {
      Info "pulling $SmallModel (1.4 GB) for the live lessons"
      try {
        Invoke-Step "ollama" @("pull", $SmallModel)
        $ollamaNote = "$SmallModel ready"; $modelReady = $true
      }
      catch { $ollamaNote = "could not pull $SmallModel - is Ollama running? start it, then: ollama pull $SmallModel" }
      if ($Models -eq "all") {
        Info "pulling $BigModel (3.4 GB)"
        try { Invoke-Step "ollama" @("pull", $BigModel) } catch { Write-Warning "could not pull $BigModel" }
      }
    }
  }

  # ----------------------------------------------------------------------------- 5. summary
  function Row($status, $what, $detail) { Write-Host ("  {0,-4}{1,-26}{2}" -f $status, $what, $detail) }
  Write-Host ""
  if ($DryRun) { Write-Host "Dry run: nothing was changed. A real run would leave:" }
  else { Write-Host "local-ai-lab is set up in $Root" }
  Write-Host ""
  Row "yes" "repository" $Root
  Row "yes" "Python packages" "in $(Join-Path $Root "venv")"
  Row $(if ($modelReady) { "yes" } else { "--" }) "local model" $ollamaNote
  if (Have "node") { Row "yes" "Node.js (--lang node)" "found" } else { Row "--" "Node.js (--lang node)" "optional: https://nodejs.org (22 or newer)" }
  if (Have "dotnet") { Row "yes" ".NET 8 (--lang csharp)" "found" } else { Row "--" ".NET 8 (--lang csharp)" "optional: https://dotnet.microsoft.com/download" }
  if ($env:TYPESAFE_API_KEY) { Row "yes" "TypeSafe key (Lesson 10)" "set" }
  else { Row "--" "TypeSafe key (Lesson 10)" "optional, for one real Jev call: https://console.typesafe.ai/keys" }
  Write-Host ""
  Write-Host $(if ($onWindows) { "Next, in Git Bash or WSL (the run script is Bash):" } else { "Next:" })
  Write-Host "  cd $Root"
  Write-Host "  ./run -l 1            # Lesson 1: the RAG web UI"
  Write-Host "  ./run -l 10 check     # Lesson 10: is this machine ready for the live parts?"
  Write-Host "  ./run -l 10 demo      # Lesson 10: the recorded scorecard, no model needed"
}
