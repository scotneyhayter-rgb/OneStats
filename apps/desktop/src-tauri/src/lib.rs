// OneStats desktop shell.
//
// In the standalone Windows build, the app launches the packaged backend (a PyInstaller *onedir*
// build bundled as a Tauri resource: onestats-server-dist/onestats-server.exe) on startup and stops it
// on exit, so the user never starts Python, FastAPI or a terminal. The backend binds to loopback only
// and brings up the local database and migrations itself (services/api/onestats/standalone/launcher.py).
//
// Onedir (not onefile) is used because a onefile exe unpacks to a temp folder and re-executes at
// runtime, which fails when the exe is spawned by a GUI process with no console. We also route the
// child's stdio to a real log file (not null/inherited) so it always has valid handles regardless of
// how the app itself was launched. The spawn outcome is recorded to sidecar.log for diagnostics.
//
// In development the bundled backend is not present, so spawning is skipped and the app uses the
// separately-running dev backend — `npm run tauri dev` keeps working unchanged.

use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use std::process::{Child, Stdio};
use std::sync::Mutex;

use tauri::{Manager, RunEvent};

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Holds the backend child process so it can be shut down cleanly when the app exits.
struct BackendProcess(Mutex<Option<Child>>);

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

fn log_dir() -> Option<PathBuf> {
    let base = std::env::var_os("LOCALAPPDATA").or_else(|| std::env::var_os("APPDATA"))?;
    let dir = PathBuf::from(base).join("OneStats").join("logs");
    std::fs::create_dir_all(&dir).ok()?;
    Some(dir)
}

fn sidecar_log(line: &str) {
    if let Some(dir) = log_dir() {
        if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(dir.join("sidecar.log")) {
            let _ = writeln!(f, "{}", line);
        }
    }
}

/// Find the packaged backend exe. Tries the bundled resource location first, then locations next to
/// the app binary, so it works whether Tauri places resources in the install dir or a subfolder.
fn find_backend(app: &tauri::AppHandle) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(res) = app.path().resource_dir() {
        candidates.push(res.join("onestats-server-dist").join("onestats-server.exe"));
        candidates.push(res.join("resources").join("onestats-server-dist").join("onestats-server.exe"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("onestats-server-dist").join("onestats-server.exe"));
            candidates.push(dir.join("onestats-server.exe")); // legacy onefile layout
        }
    }
    candidates.into_iter().find(|p| p.exists())
}

fn spawn_backend(app: &tauri::AppHandle) {
    let path = match find_backend(app) {
        Some(p) => p,
        None => {
            sidecar_log("backend not found (dev mode?) — skipping spawn");
            return;
        }
    };
    let mut cmd = std::process::Command::new(&path);
    // Real file handles for the child's stdio. A GUI app has no console, so inherited/null handles can
    // break the packaged Python process on its first write; a log file is always valid.
    if let Some(dir) = log_dir() {
        if let Ok(out) = OpenOptions::new().create(true).append(true).open(dir.join("backend-out.log")) {
            if let Ok(err) = out.try_clone() {
                cmd.stdout(Stdio::from(out)).stderr(Stdio::from(err));
            }
        }
    }
    cmd.stdin(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    match cmd.spawn() {
        Ok(child) => {
            sidecar_log(&format!("started backend: {} (pid {})", path.display(), child.id()));
            if let Some(state) = app.try_state::<BackendProcess>() {
                *state.0.lock().unwrap() = Some(child);
            }
        }
        Err(e) => sidecar_log(&format!("FAILED to start backend {}: {}", path.display(), e)),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default().plugin(tauri_plugin_opener::init());

    // In-app auto-updates: the official Tauri updater (signature-verified download/install) plus the
    // process plugin for the post-install relaunch. Desktop-only; the plugins are not built for mobile.
    #[cfg(desktop)]
    {
        builder = builder
            .plugin(tauri_plugin_updater::Builder::new().build())
            .plugin(tauri_plugin_process::init());
    }

    let app = builder
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            spawn_backend(app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet])
        .build(tauri::generate_context!())
        .expect("error while running tauri application");

    app.run(|app_handle, event| {
        // On exit, stop the backend so no orphaned process is left running.
        if let RunEvent::ExitRequested { .. } = event {
            if let Some(state) = app_handle.try_state::<BackendProcess>() {
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        }
    });
}
