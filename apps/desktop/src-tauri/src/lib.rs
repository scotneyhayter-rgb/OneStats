// OneStats desktop shell.
//
// In the standalone Windows build, the app launches the packaged backend (onestats-server.exe, sitting
// next to this app binary) on startup and stops it on exit, so the user never starts Python, FastAPI or
// a terminal. The backend binds to loopback only and brings up the local database and migrations itself
// (see services/api/onestats/standalone/launcher.py).
//
// We spawn it directly with std::process::Command (no shell-plugin scope to misconfigure) and record the
// outcome to %LOCALAPPDATA%/OneStats/logs/sidecar.log for diagnostics. In development the sidecar binary
// is not present next to the dev exe, so spawning is skipped and the app uses the separately-running dev
// backend — `npm run tauri dev` keeps working unchanged.

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

/// Resolve the packaged backend exe sitting next to this application binary.
fn sidecar_path() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?;
    let candidate = dir.join("onestats-server.exe");
    if candidate.exists() {
        Some(candidate)
    } else {
        None
    }
}

fn spawn_backend(app: &tauri::AppHandle) {
    let path = match sidecar_path() {
        Some(p) => p,
        None => {
            sidecar_log("sidecar not found next to app binary (dev mode?) — skipping spawn");
            return;
        }
    };
    let mut cmd = std::process::Command::new(&path);
    // Give the child explicit null stdio. When the app is launched from the Windows desktop/Start
    // menu (a GUI process with no console), inherited stdout/stderr handles are invalid, and the
    // packaged Python backend would fail on its first stderr write before it could start. The backend
    // logs to its own file (server.log), so it needs no console. (It worked when launched from a shell
    // only because the shell supplied valid pipes.)
    cmd.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    match cmd.spawn() {
        Ok(child) => {
            sidecar_log(&format!("started backend sidecar: {} (pid {})", path.display(), child.id()));
            if let Some(state) = app.try_state::<BackendProcess>() {
                *state.0.lock().unwrap() = Some(child);
            }
        }
        Err(e) => sidecar_log(&format!("FAILED to start backend sidecar {}: {}", path.display(), e)),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
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
