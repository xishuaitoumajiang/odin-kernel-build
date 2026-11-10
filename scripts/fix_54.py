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


def main():
    patch_obs()


if __name__ == "__main__":
    main()
