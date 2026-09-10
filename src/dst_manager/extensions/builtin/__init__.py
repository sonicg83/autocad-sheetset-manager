"""随主程序打包的内置扩展（PLAN-DM-020 / ARCH-DM-006 §4.1）。

宿主只加载 :mod:`dst_manager.extensions.builtin.index` 白名单登记的扩展，
不扫描用户目录、entry point 或文件系统。
"""
