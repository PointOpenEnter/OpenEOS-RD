fn main() {
    println!("cargo:rerun-if-changed=res/public.rc");
    println!("cargo:rerun-if-changed=assets/icon_public.ico");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        embed_resource::compile_for("res/public.rc", ["openeos"], embed_resource::NONE)
            .manifest_optional()
            .unwrap();
    }
}
