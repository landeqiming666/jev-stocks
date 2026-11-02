mod platform;

use platform::Platform;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.set_focus();
            }
        }))
        .setup(|app| {
            let p = platform::current();
            let builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title("投资逻辑哨兵")
                .inner_size(1280.0, 820.0)
                .min_inner_size(1024.0, 700.0)
                .initialization_script(p.init_script());
            p.configure_window(builder).build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
