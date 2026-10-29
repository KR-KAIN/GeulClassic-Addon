param(
    [switch]$SkipInstallerBuild
)

$env:ORT_DISABLE_TELEMETRY = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8:backslashreplace'
$OutputEncoding = New-Object System.Text.UTF8Encoding
[Console]::OutputEncoding = $OutputEncoding
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Report = Join-Path $Root 'BUILD-REPORT.txt'
# Short path fixes Windows pip/PySide6 MAX_PATH in deep Downloads folder.
$VenvDir = Join-Path $env:LOCALAPPDATA 'KAINMapleTranslator\BuildVenv0418'
$Python = Join-Path $VenvDir 'Scripts\python.exe'

function Log([string]$Message) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'), $Message)
    Write-Host $line
    Add-Content -LiteralPath $Report -Value $line -Encoding UTF8
}

function Run-Python([string[]]$Arguments, [string]$FileName, [string]$Stage) {
    $Arguments = @('-X', 'utf8', '-u') + $Arguments
    $Destination = Join-Path $Root $FileName
    Log ('START {0}' -f $Stage)
    $PreviousPref = $ErrorActionPreference
    try {
        # In Windows PowerShell 5.1, native stderr must not become a terminating error.
        $ErrorActionPreference = 'Continue'
        $global:LASTEXITCODE = 0
        & $Python @Arguments 2>&1 | Out-File -FilePath $Destination -Encoding UTF8
        $Code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousPref
    }
    if ($Code -ne 0) {
        Log ('FAILED STAGE: {0} | code={1} | file={2}' -f $Stage, $Code, $FileName)
        if (Test-Path -LiteralPath $Destination -PathType Leaf) {
            Log ('-- Last 20 lines of {0} --' -f $FileName)
            foreach ($line in @(Get-Content -LiteralPath $Destination -Tail 20)) {
                Log ('DETAIL: ' + [string]$line)
            }
        }
        throw ('{0} failed (exit {1}). See {2}' -f $Stage, $Code, $FileName)
    }
    Log ('PASS {0}' -f $Stage)
}

function Test-Python([string]$Exe, [string[]]$Selector) {
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { return $null }
    # Windows PowerShell 5.1 can strip embedded quotes from native -c arguments.
    # Use a quote-free Python probe and a file-based result instead of stdout parsing.
    $Marker = Join-Path $env:TEMP ('KAINMaple-Python-Probe-{0}.txt' -f [guid]::NewGuid().ToString('N'))
    $Probe = 'import sys,struct,pathlib;pathlib.Path(sys.argv[1]).write_text(str(sys.version_info.major*10000+sys.version_info.minor*100+struct.calcsize(chr(80))*8))'
    $Trace = ''
    $Code = 1
    $VersionCode = ''
    $PreviousPref = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $global:LASTEXITCODE = 0
        $Trace = (& $Exe @Selector -I -c $Probe $Marker 2>&1 | Out-String)
        $Code = $LASTEXITCODE
        if (Test-Path -LiteralPath $Marker -PathType Leaf) {
            $VersionCode = ([System.IO.File]::ReadAllText($Marker)).Trim()
        }
    }
    catch { $Trace = [string]$_.Exception.Message; $Code = 1 }
    finally {
        $ErrorActionPreference = $PreviousPref
        Remove-Item -LiteralPath $Marker -Force -ErrorAction SilentlyContinue
    }
    if ($Code -eq 0 -and $VersionCode -in @('31164','31264')) {
        $Version = if ($VersionCode -eq '31164') { '3.11-64' } else { '3.12-64' }
        return @{ Command=$Exe; Selector=$Selector; Version=$Version }
    }
    # Non-destructive diagnostic; allow the next candidate to be checked.
    $ProbeLog = Join-Path $Root 'PYTHON-PROBE-LOG.txt'
    $Trace = ($Trace -replace '[\r\n]+',' ').Trim()
    ('Probe failed: {0} | exit={1} | marker={2} | info={3}' -f $Exe,$Code,$VersionCode,$Trace) |
        Add-Content -LiteralPath $ProbeLog -Encoding UTF8
    return $null
}

function Find-PythonCandidates {
    # Discover interpreter installations without modifying PATH or the registry.
    $Candidates = New-Object 'System.Collections.Generic.List[string]'
    $Candidates.Add((Join-Path $env:LOCALAPPDATA 'KAINMapleTranslator\BuildPython312\python.exe'))
    foreach ($Version in @('312','311')) {
        $Candidates.Add((Join-Path $env:LOCALAPPDATA ('Programs\Python\Python{0}\python.exe' -f $Version)))
        $Candidates.Add((Join-Path $env:LOCALAPPDATA ('Programs\Python\Python{0}-64\python.exe' -f $Version)))
        $Candidates.Add(('C:\Program Files\Python{0}\python.exe' -f $Version))
        $Candidates.Add(('C:\Python{0}\python.exe' -f $Version))
    }
    # The Python bootstrapper may reuse an older existing installation instead
    # of honoring a new TargetDir (maintenance mode). Check its real location.
    foreach ($Base in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python'),
        (Join-Path $env:LOCALAPPDATA 'KAINMapleTranslator'),
        'C:\Program Files'
    )) {
        if (-not (Test-Path -LiteralPath $Base -PathType Container)) { continue }
        try {
            $Dirs = @(Get-ChildItem -LiteralPath $Base -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '^Python(311|312)(-64)?$' -or
                    ($Base -like '*KAINMapleTranslator' -and $_.Name -like 'BuildPython*') })
            foreach ($Dir in $Dirs) {
                $Candidates.Add((Join-Path $Dir.FullName 'python.exe'))
            }
        }
        catch { }
    }
    foreach ($Hive in @('HKCU:', 'HKLM:')) {
        foreach ($Version in @('3.12','3.11')) {
            $RegPath = ('{0}\Software\Python\PythonCore\{1}\InstallPath' -f $Hive,$Version)
            $Key = Get-Item -Path $RegPath -ErrorAction SilentlyContinue
            if ($null -ne $Key) {
                $Executable = $Key.GetValue('ExecutablePath')
                if ($Executable) { $Candidates.Add([string]$Executable) }
                $InstallDir = $Key.GetValue('')
                if ($InstallDir) { $Candidates.Add((Join-Path ([string]$InstallDir) 'python.exe')) }
            }
        }
    }
    foreach ($Candidate in @('python.exe','python3.exe')) {
        $Cmd = Get-Command $Candidate -ErrorAction SilentlyContinue
        if ($null -ne $Cmd -and $Cmd.Source) { $Candidates.Add($Cmd.Source) }
    }
    return @($Candidates | Select-Object -Unique)
}

function Select-Python {
    foreach ($Candidate in @(Find-PythonCandidates)) {
        $Found = Test-Python -Exe $Candidate -Selector @()
        if ($null -ne $Found) { return $Found }
    }
    $Launcher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($null -ne $Launcher) {
        foreach ($Selection in @('-3.12','-3.11')) {
            $Found = Test-Python -Exe $Launcher.Source -Selector @($Selection)
            if ($null -ne $Found) { return $Found }
        }
    }
    return $null
}

function Write-Python-Diagnostics {
    $Details = Join-Path $Root 'PYTHON-SETUP-REPORT.txt'
    ('Python installation diagnostics - {0}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) |
        Set-Content -LiteralPath $Details -Encoding UTF8
    foreach ($Candidate in @(Find-PythonCandidates)) {
        $Exists = Test-Path -LiteralPath $Candidate -PathType Leaf
        $Supported = $false
        if ($Exists) { $Supported = ($null -ne (Test-Python -Exe $Candidate -Selector @())) }
        ('Candidate: {0} | exists={1} | compatible={2}' -f $Candidate,$Exists,$Supported) |
            Add-Content -LiteralPath $Details -Encoding UTF8
    }
    $Launcher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($null -ne $Launcher) {
        ('Launcher: {0}' -f $Launcher.Source) | Add-Content -LiteralPath $Details -Encoding UTF8
        $OldPref = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            & $Launcher.Source -0p 2>&1 | Out-String |
                Add-Content -LiteralPath $Details -Encoding UTF8
        }
        catch { }
        finally { $ErrorActionPreference = $OldPref }
    }
    foreach ($LogFile in @(Get-ChildItem -LiteralPath $Root -Filter 'python-installer*' -File -ErrorAction SilentlyContinue)) {
        ('Installer log: {0}' -f $LogFile.Name) | Add-Content -LiteralPath $Details -Encoding UTF8
    }
    Log ('Python diagnostics written: {0}' -f $Details)
}

function Install-PrivatePython {
    $DownloadUrl = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
    $LocalPythonDir = Join-Path $env:LOCALAPPDATA 'KAINMapleTranslator\BuildPython312'
    $InstallerDir = Join-Path $env:TEMP 'KAINMapleTranslator-Build'
    $Installer = Join-Path $InstallerDir 'python-3.12.10-amd64.exe'
    $InstallerLog = Join-Path $Root 'python-installer.log'
    Log 'Python 3.11/3.12 x64 not detected in configured or system locations.'
    Log ('Official Python installer: {0}' -f $DownloadUrl)
    Write-Host ''
    Write-Host 'No compatible Python interpreter was found.'
    Write-Host 'The official Python 3.12 installer can be downloaded and verified.'
    Write-Host 'This installer targets CURRENT USER, does not alter system PATH.'
    Write-Host ('Requested install location: {0}' -f $LocalPythonDir)
    $Consent = Read-Host 'Install Python 3.12 for this build? Type Y to agree or N to cancel'
    if ($Consent -notmatch '^(?i:y|yes)$') {
        throw 'Python setup declined. Python 3.12 x64 can be installed manually from python.org.'
    }
    New-Item -ItemType Directory -Path $InstallerDir -Force | Out-Null
    $ValidCached = $false
    if (Test-Path -LiteralPath $Installer -PathType Leaf) {
        $Cached = Get-Item -LiteralPath $Installer
        if ($Cached.Length -gt 15000000) {
            $CachedSig = Get-AuthenticodeSignature -LiteralPath $Installer
            $ValidCached = ($CachedSig.Status -eq 'Valid' -and
                $null -ne $CachedSig.SignerCertificate -and
                $CachedSig.SignerCertificate.Subject -match 'Python Software Foundation')
        }
    }
    if ($ValidCached) {
        Log 'Reusing previously downloaded, signature-verified Python installer.'
    }
    else {
        Log 'Downloading Python installer from python.org...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $Installer -UseBasicParsing -ErrorAction Stop
    }
    $InstallerFile = Get-Item -LiteralPath $Installer
    if ($InstallerFile.Length -lt 15000000) { throw 'Python installer download appears incomplete.' }
    $Signature = Get-AuthenticodeSignature -LiteralPath $Installer
    if ($Signature.Status -ne 'Valid' -or $null -eq $Signature.SignerCertificate -or
        $Signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        throw ('Python installer signature verification failed: {0}' -f $Signature.Status)
    }
    Log 'Authenticode signature PASS (Python Software Foundation).'
    Log 'Installing Python for current user; installer log will be saved.'
    # See https://docs.python.org/3.12/using/windows.html#installing-without-ui
    $Args = @(
        '/quiet','/norestart','/log',('"{0}"' -f $InstallerLog),
        'InstallAllUsers=0',('TargetDir="{0}"' -f $LocalPythonDir),
        'Include_pip=1','Include_launcher=0','PrependPath=0',
        'Include_test=0','AssociateFiles=0','Shortcuts=0'
    )
    $Process = Start-Process -FilePath $Installer -ArgumentList $Args -Wait -PassThru
    Log ('Python installer exit code: {0}' -f $Process.ExitCode)
    if ($Process.ExitCode -notin @(0,3010)) {
        Write-Python-Diagnostics
        throw ('Python installer returned exit {0}. See python-installer.log and PYTHON-SETUP-REPORT.txt' -f $Process.ExitCode)
    }
    # Do NOT assume TargetDir was honored: a pre-existing Python installation
    # can cause the Windows installer to reuse its original directory.
    $Found = Select-Python
    if ($null -eq $Found) {
        Write-Python-Diagnostics
        throw 'Python installer finished but no working Python 3.11/3.12 x64 was detected. See PYTHON-SETUP-REPORT.txt and python-installer.log. Do not rerun the installer blindly. Also see PYTHON-PROBE-LOG.txt.'
    }
    Log ('Python located and verified: {0} ({1})' -f $Found.Command,$Found.Version)
    return $Found
}

try {
    '글클메 애드온 v0.4.54-R14-FIX1 - KAIN' | Set-Content -LiteralPath $Report -Encoding UTF8
    Log ('Build folder: {0}' -f $Root)
    Log ('PowerShell: {0}' -f $PSVersionTable.PSVersion)
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        throw 'Windows PowerShell 5.1 or newer is required.'
    }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'This builder only runs on Windows.'
    }
    if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows is required.' }
    # Previous probe results should not be mixed with this run.
    $ProbeLog = Join-Path $Root 'PYTHON-PROBE-LOG.txt'
    if (Test-Path -LiteralPath $ProbeLog -PathType Leaf) { Remove-Item -LiteralPath $ProbeLog -Force }
    $Selected = Select-Python
    if ($null -eq $Selected) { $Selected = Install-PrivatePython }
    Log ('Selected Python: {0} ({1})' -f $Selected.Command, $Selected.Version)
    # Self-contained ZIP verification: fail early if archive was only partly extracted.
    $RequiredPaths = @(
        'launch.py', 'requirements.txt', 'kain_maple_translator\main.py',
        'kain_maple_translator\core.py', 'kain_maple_translator\worker.py',
        'kain_maple_translator\vision.py', 'kain_maple_translator\glossary.py',
        'kain_maple_translator\translation.py', 'kain_maple_translator\item_catalog.py', 'kain_maple_translator\expanded_terms.py', 'kain_maple_translator\layout.py',
        'kain_maple_translator\game_window.py', 'kain_maple_translator\wgc_capture.py', 'kain_maple_translator\obs_source.py',
        'kain_maple_translator\window_behavior.py', 'kain_maple_translator\visual_theme.py',
        'kain_maple_translator\natural_trade.py', 'kain_maple_translator\chat_render.py',
        'tests\test_v040_render_trade_themes.py',
        'scripts\fetch_classic_world_open_data.py',
        'scripts\prepare_offline_models.py',
        'scripts\check_offline_models.py', 'scripts\check_ocr_models.py',
        'kain_maple_translator\fast_vision.py',
        'kain_maple_translator\linked_ocr.py', 'kain_maple_translator\source_palette.py',
        'kain_maple_translator\recognition_batch.py', 'kain_maple_translator\link_integrity.py',
        'tests\test_v0428_linked_palette.py', 'scripts\benchmark_linked_labels.py',
        'tests\fixtures\user-native-palette-rows.png', 'tests\fixtures\linked-labels-v28\labels.json',
        'tests\fixtures\linked-labels-v28\ko-26.png',
        'tests\fixtures\linked-labels-v28\korean-link-crop.png',
    'kain_maple_translator\ink_background.py',
    'kain_maple_translator\trade_stats.py', 'kain_maple_translator\ocr_validation.py',
    'tests\test_v0427_scroll_stats.py', 'kain_maple_translator\capture_stream.py',
        'kain_maple_translator\translation_queue.py', 'kain_maple_translator\row_admission.py',
        'kain_maple_translator\trade_memory.py', 'kain_maple_translator\timings.py',
        'kain_maple_translator\frame_context.py', 'kain_maple_translator\badge_split.py',
        'kain_maple_translator\runtime_metrics.py', 'kain_maple_translator\console_io.py',
        'resources\chat-templates\channel-coin.png',
        'kain_maple_translator\chat_shorthand.py', 'kain_maple_translator\system_notices.py',
        'scripts\replay_ocr_fixtures.py', 'scripts\runtime_privacy_hook.py',
        'tests\fixtures\user-four-colour-rows.png', 'tests\test_v0426_separator_regression.py',
        'resources\ocr\model-manifest.json',
        'kain_maple_translator\image_io.py', 'kain_maple_translator\stack_digits.py',
        'kain_maple_translator\chat_history.py', 'kain_maple_translator\history_dialog.py',
        'resources\hunt\digits\manifest.json',
        'resources\hunt\potions\manifest.json', 'scripts\check_potion_assets.py',
        'tests\test_core.py',
        'tests\test_glossary.py', 'tests\test_python_bootstrap.py',
        'tests\test_windows_build.py'
    )
    foreach ($RelativePath in $RequiredPaths) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $RelativePath) -PathType Leaf)) {
            throw ('ZIP extraction incomplete. Missing bundled file: {0}' -f $RelativePath)
        }
    }
    Log 'Source bundle self-check PASS (no earlier-version folders required).'
    Set-Location -LiteralPath $Root
    # Only reuse the isolated environment inside THIS folder. Verify it is executable.
    if (Test-Path -LiteralPath $Python -PathType Leaf) {
        $OldPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $global:LASTEXITCODE = 0
            & $Python --version 2>&1 | Out-File -FilePath (Join-Path $Root 'venv-check.txt') -Encoding UTF8
            $CurrentCode = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $OldPreference }
        if ($CurrentCode -ne 0) { throw 'Bundled virtual environment in this folder cannot run. See venv-check.txt. Extract a fresh ZIP.' }
    }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        Log 'Creating isolated Python environment...'
        $PreviousPref = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $global:LASTEXITCODE = 0
            $Launcher = $Selected.Command
            $LauncherArgs = @($Selected.Selector)
            & $Launcher @LauncherArgs -m venv $VenvDir 2>&1 |
                Out-File -FilePath (Join-Path $Root 'venv-log.txt') -Encoding UTF8
            $Code = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $PreviousPref }
        if ($Code -ne 0 -or -not (Test-Path -LiteralPath $Python -PathType Leaf)) {
            throw 'Python virtual environment creation failed. See venv-log.txt'
        }
    }
    Log ('Build environment: {0} (outside deep ZIP path)' -f $VenvDir)
    Run-Python @('-m','pip','install','--disable-pip-version-check','-r',(Join-Path $Root 'requirements.txt')) 'pip-log.txt' 'Install dependencies'
    Run-Python @('-m','scripts.build_info_r8') 'BUILD-INFO-R8.txt' 'Record build Python and monotonic clock'
    Run-Python @('-m','scripts.run_tests') 'TEST-REPORT.txt' 'Logic and builder tests'
    # Ensure optional resource destinations exist even without an internet response.
    # Only verified source exports are used as input; these directory checks do not
    # invent data or falsely report downloads as complete.
    foreach ($Relative in @('resources\item-ids','resources\open-classic','resources\models')) {
        $Folder = Join-Path $Root $Relative
        if (-not (Test-Path -LiteralPath $Folder -PathType Container)) {
            New-Item -ItemType Directory -Path $Folder -Force | Out-Null
        }
    }
    # Public GMS v83 item-ID snapshot. No NiaMeowDB access. This is a
    # best-effort supplement: network outages must not prevent app builds.
    try {
        Run-Python @('-m','scripts.build_classic_index','--root',$Root) 'ITEM-ID-BUILD-LOG.txt' 'Build old-school item ID index'
    }
    catch {
        Log ('WARNING: Public GMS item-ID index not available. See ITEM-ID-BUILD-LOG.txt: '+[string]$_.Exception.Message)
    }
    # Download the publisher's explicit CC BY-NC-SA JSON exports (noncommercial).
    # Keep existing offline dataset if its server is temporarily unavailable.
    try {
        Run-Python @('-m','scripts.fetch_classic_world_open_data','--root',$Root) 'OPEN-DATA-BUILD-LOG.txt' 'Download licensed Classic World offline data'
    }
    catch {
        Log ('WARNING: Licensed open data incomplete. See OPEN-DATA-REPORT.json: '+[string]$_.Exception.Message)
    }
    Run-Python @('-m','scripts.prepare_offline_models') 'MODEL-REPORT.txt' 'Download and validate EN/KO offline models'
    Run-Python @('-m','scripts.check_potion_assets') 'POTION-ASSET-REPORT.txt' 'Verify bundled Global Classic potion PNGs'
    Run-Python @('-m','scripts.check_ocr_models') 'OCR-MODEL-REPORT.txt' 'Verify bundled OCR models and real recognition'
    Run-Python @('-m','scripts.replay_ocr_fixtures') 'OCR-REPLAY-REPORT.txt' 'Replay actual game chat regression crops'
    Run-Python @('-m','scripts.check_offline_models') 'MODEL-TRANSLATION-REPORT.txt' 'Verify real offline EN/KO translation'
    Run-Python @('-c','import sys,PySide6.QtWidgets,mss,cv2,rapidocr,onnxruntime,ctranslate2,sentencepiece,windows_capture;import kain_maple_translator.main;print(sys.version)') 'import-check.txt' 'Runtime imports'
    if ($SkipInstallerBuild) {
        Log 'SKIPPED Windows executable packaging (explicit -SkipInstallerBuild)'
        exit 0
    }
    $Arguments = @(
        '-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
        '--name','글클메 애드온',
        '--runtime-hook',(Join-Path $Root 'scripts\runtime_privacy_hook.py'),
        '--collect-all','rapidocr',
        '--collect-all','onnxruntime',
        '--collect-all','mss',
        '--collect-all','windows_capture',
        '--collect-all','ctranslate2',
        '--collect-all','sentencepiece',
        '--add-data',((Join-Path $Root 'resources\chat-templates') + ';resources\chat-templates'),
        '--add-data',((Join-Path $Root 'resources\ocr') + ';resources\ocr'),
        '--add-data',((Join-Path $Root 'resources\hunt') + ';resources\hunt'),
        '--add-data',((Join-Path $Root 'resources\models') + ';resources\models'),
        '--add-data',((Join-Path $Root 'resources\item-ids') + ';resources\item-ids'),
        '--add-data',((Join-Path $Root 'resources\open-classic') + ';resources\open-classic'),
        '--add-data',((Join-Path $Root 'resources\classic_ui') + ';resources\classic_ui'),
        '--add-data',((Join-Path $Root 'resources\help') + ';resources\help'),
        '--add-data',((Join-Path $Root 'resources\item-info') + ';resources\item-info'),
        '--hidden-import','PySide6.QtWidgets',
        '--hidden-import','PySide6.QtCore',
        '--hidden-import','PySide6.QtGui',
        'launch.py'
    )
    # meowdb item names are optional: kept out of the public repository (their
    # redistribution needs the site operator's permission), bundled only if present.
    if (Get-ChildItem -Path (Join-Path $Root 'resources\meowdb') -Filter *.json -ErrorAction SilentlyContinue) {
        $Arguments = $Arguments[0..($Arguments.Count-2)] + @('--add-data',((Join-Path $Root 'resources\meowdb') + ';resources\meowdb'),'launch.py')
    }
    Run-Python $Arguments 'pyinstaller-log.txt' 'Build standalone Windows EXE'
    $Exe = Join-Path $Root 'dist\글클메 애드온\글클메 애드온.exe'
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
        throw 'PyInstaller reported success but the executable is missing.'
    }
    $File = Get-Item -LiteralPath $Exe
    if ($File.Length -le 0) { throw 'Executable file is empty.' }
    foreach ($Direction in @('en_ko','ko_en')) {
        $Model=Join-Path $Root ('dist\글클메 애드온\_internal\resources\models\translate-'+$Direction+'.argosmodel')
        if (-not (Test-Path -LiteralPath $Model -PathType Leaf)) { throw ('EXE packaged model missing: {0}' -f $Direction) }
    }
    $Hash = Get-FileHash -LiteralPath $Exe -Algorithm SHA256
    Log ('EXE: {0}' -f $Exe)
    Log ('EXE BYTES: {0}' -f $File.Length)
    Log ('SHA256: {0}' -f $Hash.Hash)
    Log 'BUILD PASS - EXE and EN/KO models packaged. Actual gameplay and OCR still need Windows validation.'
    exit 0
}
catch {
    Log ('BUILD FAILED: {0}' -f $_.Exception.Message)
    Write-Host 'A stage failed. See the listed report file(s).' -ForegroundColor Red
    exit 1
}
