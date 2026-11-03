// Next Trainer Windows launcher (#435): a thin shell around the portable package.
//
// It delegates the actual app startup to Next-Trainer/scripts/portable/launch_portable.bat
// (which owns the embedded-Python environment policy and evolves with the repo), opens the
// browser once the GUI port answers, relays the app log into this console, and owns the
// stop / update loop:
//   Q - stop the app tree and exit
//   U - stop the app, run the package updater (检查更新), then offer to restart

using System.Diagnostics;

const int GuiPort = 28000;
const int GuiWaitMinutes = 15; // first launch may verify embedded dependencies

var root = Path.GetFullPath(AppContext.BaseDirectory);
var selfTest = args.Contains("--selftest", StringComparer.OrdinalIgnoreCase);

Console.Title = "Next Trainer";
Console.OutputEncoding = System.Text.Encoding.UTF8;

Log("Next Trainer 启动器");
Log($"包根目录: {root}");

// The launcher ships at the package root; tolerate it being moved into tools\.
var launchScript = Path.Combine(root, "Next-Trainer", "scripts", "portable", "launch_portable.bat");
if (!File.Exists(launchScript))
{
    var parent = Directory.GetParent(root)?.FullName;
    if (parent is not null)
    {
        var candidate = Path.Combine(parent, "Next-Trainer", "scripts", "portable", "launch_portable.bat");
        if (File.Exists(candidate))
        {
            root = parent;
            launchScript = candidate;
        }
    }
}
if (!File.Exists(launchScript))
{
    return Fail("找不到 Next-Trainer\\scripts\\portable\\launch_portable.bat，请确认整合包已完整解压。");
}
Log($"启动脚本: {launchScript}");

Process? child = null;
Console.CancelKeyPress += (_, e) =>
{
    e.Cancel = true;
    StopTree(child);
    Environment.Exit(0);
};

var startError = StartApp();
if (startError is not null) return Fail(startError);
if (child is null) return Fail("无法启动训练进程（未知原因）");

var guiUrl = $"http://127.0.0.1:{GuiPort}";
Log($"正在启动（首次运行会校验内嵌依赖，可能要几分钟）。GUI: {guiUrl}");
Log("按 Q 停止并退出 · 按 U 检查更新（会先停止服务）");

if (selfTest)
{
    var ok = await WaitForGui(guiUrl, TimeSpan.FromMinutes(GuiWaitMinutes), child);
    StopTree(child);
    if (!ok) return Fail($"GUI 端口 {GuiPort} 在 {GuiWaitMinutes} 分钟内未就绪");
    Log("[selftest] 端口就绪，退出");
    return 0;
}

// Background: open the browser once the GUI answers; keep the console free for keys.
_ = Task.Run(async () =>
{
    if (await WaitForGui(guiUrl, TimeSpan.FromMinutes(GuiWaitMinutes), child))
    {
        OpenBrowser(guiUrl);
        return;
    }
    if (child is not null && child.HasExited)
    {
        Log("服务进程已退出，请查看上面的日志。");
        return;
    }
    Log($"GUI 端口 {GuiPort} 超时未就绪（服务可能仍在初始化），请稍后手动访问 {guiUrl}");
});

var exitTask = child.WaitForExitAsync();
while (!exitTask.IsCompleted)
{
    if (Console.KeyAvailable)
    {
        var key = Console.ReadKey(intercept: true).Key;
        if (key is ConsoleKey.Q or ConsoleKey.Escape)
        {
            Log("正在停止服务…");
            StopTree(child);
            return 0;
        }
        if (key is ConsoleKey.U)
        {
            var restart = await RunUpdateAsync();
            if (restart is null) return 0;
            child = restart;
            exitTask = child.WaitForExitAsync();
        }
    }
    await Task.Delay(200);
}
Log("服务进程已退出。");
return 0;

string? StartApp()
{
    var psi = new ProcessStartInfo
    {
        FileName = "cmd.exe",
        Arguments = $"/c \"{launchScript}\"",
        WorkingDirectory = root,
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        CreateNoWindow = false,
    };
    psi.Environment["PYTHONUTF8"] = "1";
    try
    {
        child = Process.Start(psi);
    }
    catch (Exception exc)
    {
        return $"启动失败: {exc.Message}";
    }
    if (child is null) return "启动失败: 进程未创建";
    child.OutputDataReceived += (_, e) => { if (e.Data is not null) Console.WriteLine(e.Data); };
    child.ErrorDataReceived += (_, e) => { if (e.Data is not null) Console.WriteLine(e.Data); };
    child.BeginOutputReadLine();
    child.BeginErrorReadLine();
    return null;
}

async Task<Process?> RunUpdateAsync()
{
    var candidates = new[]
    {
        Path.Combine(root, "检查更新.bat"),
        Path.Combine(root, "tools", "Update-Next-Trainer.bat"),
    };
    var updateScript = candidates.FirstOrDefault(File.Exists);
    if (updateScript is null)
    {
        Log("未找到更新脚本（检查更新.bat / tools\\Update-Next-Trainer.bat），请确认整合包完整。");
        return child;
    }

    Log("正在停止服务以检查更新…");
    StopTree(child);
    child = null;

    Log($"运行 {updateScript}");
    var psi = new ProcessStartInfo
    {
        FileName = "cmd.exe",
        Arguments = $"/c \"{updateScript}\"",
        WorkingDirectory = root,
        UseShellExecute = false,
    };
    var updater = Process.Start(psi);
    if (updater is null)
    {
        Log("无法启动更新脚本。");
        return null;
    }
    await updater.WaitForExitAsync();

    Log("按 R 重启服务，按其它键退出。");
    var key = Console.ReadKey(intercept: true).Key;
    if (key is not ConsoleKey.R) return null;
    var startError = StartApp();
    if (startError is not null)
    {
        Log(startError);
        return null;
    }
    return child;
}

async Task<bool> WaitForGui(string url, TimeSpan timeout, Process? process)
{
    using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
    var deadline = DateTime.UtcNow + timeout;
    var attempts = 0;
    while (DateTime.UtcNow < deadline)
    {
        if (process is not null && process.HasExited) return false;
        attempts += 1;
        if (attempts % 15 == 0) Log("仍在初始化（首次会校验内嵌依赖，可能要几分钟）…");
        try
        {
            using var response = await client.GetAsync(url);
            if (response.IsSuccessStatusCode)
            {
                Log($"GUI 就绪: {url}");
                return true;
            }
        }
        catch
        {
            // Not ready yet.
        }
        await Task.Delay(1000);
    }
    return false;
}

void StopTree(Process? process)
{
    if (process is null || process.HasExited) return;
    try
    {
        process.Kill(entireProcessTree: true);
        process.WaitForExit(10_000);
    }
    catch (Exception exc)
    {
        Log($"停止服务失败: {exc.Message}");
    }
}

void OpenBrowser(string url)
{
    try
    {
        Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        Log($"已打开 {url}");
    }
    catch (Exception exc)
    {
        Log($"打开浏览器失败（{exc.Message}），请手动访问 {url}");
    }
}

int Fail(string message)
{
    Console.WriteLine($"[错误] {message}");
    Console.WriteLine("按任意键退出…");
    try { Console.ReadKey(intercept: true); } catch { /* console unavailable */ }
    return 1;
}

void Log(string message) => Console.WriteLine($"[launcher] {message}");
