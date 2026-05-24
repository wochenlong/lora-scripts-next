"""Patch vendored layout bundle for cross-page config import validation (#43)."""
from __future__ import annotations

from pathlib import Path

LAYOUT = Path("frontend/dist/assets/layout.96d49288.js")

HELPER_MARKER = "mikazukiApplyImportedConfig=async("
HELPER = (
    "mikazukiApplyImportedConfig=async(k,t,schemaFn,a,successMsg,merge)=>{"
    'const resp=await fetch("/api/config/validate-import",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({page_train_type:t,config:k})});'
    'if(!resp.ok)throw new Error("\\u5bfc\\u5165\\u5931\\u8d25\\uff1a\\u7f51\\u7edc\\u9519\\u8bef");'
    "const payload=await resp.json();"
    'if(payload.status!=="success")throw new Error(payload.message||"\\u5bfc\\u5165\\u5931\\u8d25");'
    "const data=payload.data;"
    'if(data.result==="reject"){ElMessage.error((data.errors||["\\u5bfc\\u5165\\u5931\\u8d25"]).join("\\n"));return!1}'
    'if(data.result==="redirect"){try{await ElMessageBox.confirm(data.message,"\\u914d\\u7f6e\\u7c7b\\u578b\\u4e0d\\u5339\\u914d",{confirmButtonText:"\\u8df3\\u8f6c\\u5e76\\u5bfc\\u5165",cancelButtonText:"\\u53d6\\u6d88",type:"warning"});sessionStorage.setItem("mikazuki-pending-import",JSON.stringify(data.config));location.href=data.target_path;return!1}catch(e){return!1}}'
    "const cfg=data.config||k;"
    "let U=findChangedDataBySchema(cfg,schemaFn);"
    "if(data.forced_train_type)U.model_train_type=data.forced_train_type;"
    "merge?a.value==null?a.value=clone(U):a.value=Object.assign({},a.value,U):a.value=U;"
    'if(successMsg)ElMessage.success(successMsg);'
    "return!0}"
)

REPLACEMENTS: list[tuple[str, str, str]] = [
    (
        "helper anchor",
        "return l},data$1={",
        f"return l}},{HELPER},data$1={{",
    ),
    (
        "toml import",
        (
            "N.onload=D=>{const V=D.target.result;try{let k=TomlParse(V),"
            "U=findChangedDataBySchema(k,n.value);a.value=U,ElMessage.success("
            '"\\u5BFC\\u5165\\u6210\\u529F")}catch(k){console.log(k),'
            'ElMessage.error("\\u5BFC\\u5165\\u5931\\u8D25")}}'
        ),
        (
            "N.onload=async D=>{const V=D.target.result;try{let k=TomlParse(V);"
            "await mikazukiApplyImportedConfig(k,t,n.value,a,"
            '"\\u5BFC\\u5165\\u6210\\u529F")}catch(k){console.log(k),'
            'ElMessage.error(typeof k=="string"?k:k.message||"\\u5BFC\\u5165\\u5931\\u8D25")}}'
        ),
    ),
    (
        "preset merge",
        (
            "$=_=>{let m=findChangedDataBySchema(_,n.value);"
            "a.value==null?a.value=clone(m):a.value=Object.assign({},a.value,m),"
            "console.log(a.value)}"
        ),
        "$=async _=>{await mikazukiApplyImportedConfig(_,t,n.value,a,null,!0)}",
    ),
    (
        "preset apply",
        'W=_=>{$(_),p.value=!1,ElMessage.success("\\u5DF2\\u5C06\\u6A21\\u677F\\u5E94\\u7528\\u81F3\\u5F53\\u524D\\u53C2\\u6570")}',
        (
            'W=async _=>{if(await mikazukiApplyImportedConfig(_,t,n.value,a,'
            '"\\u5DF2\\u5C06\\u6A21\\u677F\\u5E94\\u7528\\u81F3\\u5F53\\u524D\\u53C2\\u6570"))p.value=!1}'
        ),
    ),
    (
        "history apply",
        (
            'Y=(_,m)=>{a.value=clone(m.value),i.value=!1,ElMessage.success('
            '"\\u5DF2\\u5C06\\u5386\\u53F2\\u53C2\\u6570\\u5E94\\u7528\\u81F3\\u5F53\\u524D\\u53C2\\u6570")}'
        ),
        (
            'Y=async (_,m)=>{if(await mikazukiApplyImportedConfig(clone(m.value),t,n.value,a,'
            '"\\u5DF2\\u5C06\\u5386\\u53F2\\u53C2\\u6570\\u5E94\\u7528\\u81F3\\u5F53\\u524D\\u53C2\\u6570"))i.value=!1}'
        ),
    ),
    (
        "pending import on mount",
        "onMounted(async()=>{I(),y()})",
        (
            "onMounted(async()=>{I();const pi=sessionStorage.getItem("
            '"mikazuki-pending-import");if(pi){sessionStorage.removeItem('
            '"mikazuki-pending-import");try{const cfg=JSON.parse(pi);'
            "await mikazukiApplyImportedConfig(cfg,t,n.value,a,"
            '"\\u5df2\\u5728\\u76ee\\u6807\\u9875\\u9762\\u5bfc\\u5165\\u914d\\u7f6e")'
            '}catch(e){console.log(e)}}y()})'
        ),
    ),
]


def main() -> None:
    text = LAYOUT.read_text(encoding="utf-8")
    if HELPER_MARKER in text:
        print("already patched")
        return

    for label, old, new in REPLACEMENTS:
        if old not in text:
            raise SystemExit(f"patch anchor not found: {label}")
        text = text.replace(old, new, 1)

    LAYOUT.write_text(text, encoding="utf-8")
    print("patched", LAYOUT)


if __name__ == "__main__":
    main()
