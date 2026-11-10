#!/usr/bin/env python3
"""5.4 兼容补丁：把驱动里依赖新内核 API 的地方改成 5.4 可用写法。"""
import io
import os
import re
import sys

KROOT = sys.argv[1] if len(sys.argv) > 1 else "kernel"
DRV = os.path.join(KROOT, "drivers", "kernelsu")


def read(p):
    with io.open(p, "r", encoding="utf-8", errors="surrogateescape") as f:
        return f.read()


def write(p, s):
    with io.open(p, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(s)


def patch_obs():
    p = os.path.join(DRV, "manager", "pkg_observer.c")
    if not os.path.exists(p):
        print("pkg_observer: missing, skip")
        return
    s = read(p)
    old = """static const struct fsnotify_ops ksu_ops = {
    .handle_inode_event = ksu_handle_inode_event,
};"""
    if old not in s:
        print("pkg_observer: ops block not found, skip")
        return
    new = """#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)
static int ksu_handle_event_compat(struct fsnotify_group *group, struct inode *inode,
                                   u32 mask, const void *data, int data_type,
                                   const struct qstr *file_name, u32 cookie,
                                   struct fsnotify_iter_info *iter_info)
{
    if (!file_name)
        return 0;
    if (inode && S_ISDIR(inode->i_mode))
        return 0;
    if (file_name->len == 13 && !memcmp(file_name->name, "packages.list", 13)) {
        pr_info("packages.list detected: %d\\n", mask);
        ksu_defer_track_throne();
    }
    return 0;
}
static const struct fsnotify_ops ksu_ops = {
    .handle_event = ksu_handle_event_compat,
};
#else
static const struct fsnotify_ops ksu_ops = {
    .handle_inode_event = ksu_handle_inode_event,
};
#endif"""
    s = s.replace(old, new, 1)
    # 未使用的旧 handler 在 5.4 上会报 -Wunused
    s = s.replace("static int ksu_handle_inode_event(", "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 9, 0)\nstatic int ksu_handle_inode_event(", 1)
    s = s.replace("""        ksu_defer_track_throne();
    }
    return 0;
}

#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)""", """        ksu_defer_track_throne();
    }
    return 0;
}
#endif

#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)""", 1)
    write(p, s)
    print("pkg_observer patched")


def patch_twa():
    import glob
    blk = "#ifndef TWA_RESUME\n#define TWA_RESUME true\n#endif\n"
    for p in glob.glob(os.path.join(DRV, "**", "*.c"), recursive=True):
        s = read(p)
        if "TWA_RESUME" not in s:
            continue
        if "#define TWA_RESUME" in s:
            continue
        s = blk + s
        write(p, s)
        print("TWA_RESUME compat ->", p)


def patch_cpu_spoof():
    p = os.path.join(DRV, "extension", "cpu_spoof.c")
    if not os.path.exists(p):
        return
    s = read(p)
    target = "                        (*curr_cs_ptr)->vdso_clock_mode =\n                            VDSO_CLOCKMODE_ARCHTIMER;\n"
    if target in s:
        s = s.replace(
            target,
            "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 6, 0)\n" + target +
            "#else\n                        (void)curr_cs_ptr;\n#endif\n", 1)
        write(p, s)
        print("cpu_spoof patched")
    else:
        print("cpu_spoof: pattern not found")


def patch_app_profile():
    p = os.path.join(DRV, "policy", "app_profile.c")
    if not os.path.exists(p):
        print("app_profile: missing, skip")
        return
    s = read(p)
    line = "    atomic_set(&current->seccomp.filter_count, 0);\n"
    if line in s:
        s = s.replace(line, "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 9, 0)\n" + line + "#endif\n", 1)
        write(p, s)
        print("app_profile patched")
    else:
        print("app_profile: filter_count line not found")


def relax_werror():
    p = os.path.join(DRV, "Kbuild")
    if not os.path.exists(p):
        return
    s = read(p)
    if "-Werror" in s:
        s = s.replace("-Werror", "-Wno-error")
        write(p, s)
        print("Kbuild: -Werror relaxed (诊断轮)")


def main():
    patch_obs()
    patch_twa()
    patch_app_profile()
    patch_cpu_spoof()
    if os.environ.get("KSU_RELAX_WERROR") == "1":
        relax_werror()


if __name__ == "__main__":
    main()
