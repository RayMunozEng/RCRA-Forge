"""Bounded Windows graphics diagnostics on a desktop that is never activated.

This is a development capture helper, not a sandbox for untrusted programs.
The child is assigned to our kill-on-close job while suspended. By default its
job blocks desktop switching and display-setting changes. Launchers which create
their own nested UI jobs can explicitly omit those additional restrictions;
the separate desktop and owned-process cleanup still apply. No input is sent.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid


class STARTUPINFO(C.Structure):
    _fields_ = [("cb", W.DWORD), ("lpReserved", W.LPWSTR),
                ("lpDesktop", W.LPWSTR), ("lpTitle", W.LPWSTR),
                ("dwX", W.DWORD), ("dwY", W.DWORD),
                ("dwXSize", W.DWORD), ("dwYSize", W.DWORD),
                ("dwXCountChars", W.DWORD), ("dwYCountChars", W.DWORD),
                ("dwFillAttribute", W.DWORD), ("dwFlags", W.DWORD),
                ("wShowWindow", W.WORD), ("cbReserved2", W.WORD),
                ("lpReserved2", C.POINTER(W.BYTE)), ("hStdInput", W.HANDLE),
                ("hStdOutput", W.HANDLE), ("hStdError", W.HANDLE)]


class PROCESS_INFORMATION(C.Structure):
    _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE),
                ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]


class BASIC_LIMIT(C.Structure):
    _fields_ = [("PerProcessUserTimeLimit", C.c_longlong),
                ("PerJobUserTimeLimit", C.c_longlong), ("LimitFlags", W.DWORD),
                ("MinimumWorkingSetSize", C.c_size_t),
                ("MaximumWorkingSetSize", C.c_size_t),
                ("ActiveProcessLimit", W.DWORD), ("Affinity", C.c_size_t),
                ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]


class IO_COUNTERS(C.Structure):
    _fields_ = [(name, C.c_ulonglong) for name in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class EXTENDED_LIMIT(C.Structure):
    _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", C.c_size_t), ("JobMemoryLimit", C.c_size_t),
                ("PeakProcessMemoryUsed", C.c_size_t),
                ("PeakJobMemoryUsed", C.c_size_t)]


class MEMORY_STATUS(C.Structure):
    _fields_ = [("dwLength", W.DWORD), ("dwMemoryLoad", W.DWORD),
                ("ullTotalPhys", C.c_ulonglong),
                ("ullAvailPhys", C.c_ulonglong),
                ("ullTotalPageFile", C.c_ulonglong),
                ("ullAvailPageFile", C.c_ulonglong),
                ("ullTotalVirtual", C.c_ulonglong),
                ("ullAvailVirtual", C.c_ulonglong),
                ("ullAvailExtendedVirtual", C.c_ulonglong)]


class JOB_PIDS(C.Structure):
    _fields_ = [("assigned", W.DWORD), ("count", W.DWORD),
                ("pids", C.c_size_t * 1024)]


def api():
    if os.name != "nt":
        raise RuntimeError("This capture helper requires Windows")
    user = C.WinDLL("user32", use_last_error=True)
    kernel = C.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateDesktopW": (W.HANDLE, [W.LPCWSTR, W.LPCWSTR, W.LPVOID, W.DWORD, W.DWORD, W.LPVOID]),
        "CloseDesktop": (W.BOOL, [W.HANDLE]),
        "OpenInputDesktop": (W.HANDLE, [W.DWORD, W.BOOL, W.DWORD]),
        "GetThreadDesktop": (W.HANDLE, [W.DWORD]),
        "GetProcessWindowStation": (W.HANDLE, []),
        "GetUserObjectInformationW": (W.BOOL, [W.HANDLE, C.c_int, W.LPVOID, W.DWORD, C.POINTER(W.DWORD)]),
        "GetWindowThreadProcessId": (W.DWORD, [W.HWND, C.POINTER(W.DWORD)]),
        "GetWindowTextW": (C.c_int, [W.HWND, W.LPWSTR, C.c_int]),
        "GetClassNameW": (C.c_int, [W.HWND, W.LPWSTR, C.c_int]),
        "IsWindowVisible": (W.BOOL, [W.HWND]),
        "GetWindowRect": (W.BOOL, [W.HWND, C.POINTER(W.RECT)]),
    }
    for name, (result, args) in signatures.items():
        function = getattr(user, name)
        function.restype, function.argtypes = result, args
    for name, result, args in [
        ("GetCurrentThreadId", W.DWORD, []),
        ("CreateJobObjectW", W.HANDLE, [W.LPVOID, W.LPCWSTR]),
        ("SetInformationJobObject", W.BOOL, [W.HANDLE, C.c_int, W.LPVOID, W.DWORD]),
        ("QueryInformationJobObject", W.BOOL, [W.HANDLE, C.c_int, W.LPVOID, W.DWORD, C.POINTER(W.DWORD)]),
        ("AssignProcessToJobObject", W.BOOL, [W.HANDLE, W.HANDLE]),
        ("TerminateJobObject", W.BOOL, [W.HANDLE, W.UINT]),
        ("TerminateProcess", W.BOOL, [W.HANDLE, W.UINT]),
        ("GetExitCodeProcess", W.BOOL, [W.HANDLE, C.POINTER(W.DWORD)]),
        ("ResumeThread", W.DWORD, [W.HANDLE]),
        ("CloseHandle", W.BOOL, [W.HANDLE]),
        ("WaitForSingleObject", W.DWORD, [W.HANDLE, W.DWORD]),
        ("GlobalMemoryStatusEx", W.BOOL, [C.POINTER(MEMORY_STATUS)]),
        ("CreateProcessW", W.BOOL, [W.LPCWSTR, W.LPWSTR, W.LPVOID, W.LPVOID,
                                   W.BOOL, W.DWORD, W.LPVOID, W.LPCWSTR,
                                   C.POINTER(STARTUPINFO), C.POINTER(PROCESS_INFORMATION)]),
    ]:
        function = getattr(kernel, name)
        function.restype, function.argtypes = result, args
    return user, kernel


def check(result):
    if not result:
        raise C.WinError(C.get_last_error())
    return result


def object_name(user, handle):
    name, needed = C.create_unicode_buffer(512), W.DWORD()
    check(user.GetUserObjectInformationW(handle, 2, name, C.sizeof(name), C.byref(needed)))
    return name.value


def desktop_state(user, kernel):
    active = check(user.OpenInputDesktop(0, False, 1))
    try:
        return {
            "window_station": object_name(user, user.GetProcessWindowStation()),
            "thread_desktop": object_name(user, user.GetThreadDesktop(kernel.GetCurrentThreadId())),
            "input_desktop": object_name(user, active),
        }
    finally:
        user.CloseDesktop(active)


def record_final_desktop(report, user, kernel):
    # The secure/input desktop can become unreadable during shutdown. The job
    # has already been terminated: preserve the original error and final report
    # without claiming that an inaccessible desktop was verified safe.
    try:
        report["after"] = desktop_state(user, kernel)
    except OSError as error:
        report["after"] = {"input_desktop": None, "error": str(error)}
        report["cleanup_desktop_error"] = str(error)
        if report.get("status") == "exited":
            report.update(status="error", error="Final input desktop could not be verified: " + str(error))


def windows(user, desktop):
    result = []
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    @callback_type
    def callback(window, _):
        pid, rect = W.DWORD(), W.RECT()
        thread = user.GetWindowThreadProcessId(window, C.byref(pid))
        title, cls = C.create_unicode_buffer(512), C.create_unicode_buffer(256)
        user.GetWindowTextW(window, title, len(title))
        user.GetClassNameW(window, cls, len(cls))
        user.GetWindowRect(window, C.byref(rect))
        result.append({"hwnd": int(window), "pid": pid.value, "thread": thread,
                       "title": title.value, "class": cls.value,
                       "visible": bool(user.IsWindowVisible(window)),
                       "rect": [rect.left, rect.top, rect.right, rect.bottom]})
        return True

    user.EnumDesktopWindows.argtypes = [W.HANDLE, callback_type, W.LPARAM]
    user.EnumDesktopWindows.restype = W.BOOL
    C.set_last_error(0)
    if not user.EnumDesktopWindows(desktop, callback, 0) and C.get_last_error():
        raise C.WinError(C.get_last_error())
    return result


def write_report(path, report):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Windows readers/cloud sync can briefly hold a non-delete-sharing handle.
    # A status reader must not inadvertently terminate the capture process tree.
    for attempt in range(40):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.05)


def resource_state(kernel, disk_path):
    memory = MEMORY_STATUS()
    memory.dwLength = C.sizeof(memory)
    check(kernel.GlobalMemoryStatusEx(C.byref(memory)))
    return {
        "available_physical_gib": memory.ullAvailPhys / 1024**3,
        "available_pagefile_gib": memory.ullAvailPageFile / 1024**3,
        "free_disk_gib": shutil.disk_usage(disk_path).free / 1024**3,
    }


def job_memory_state(kernel, job):
    """Return current job accounting without weakening its hard memory limit."""
    limits = EXTENDED_LIMIT()
    check(kernel.QueryInformationJobObject(
        job, 9, C.byref(limits), C.sizeof(limits), None))
    return {
        "peak_process_gib": limits.PeakProcessMemoryUsed / 1024**3,
        "peak_job_gib": limits.PeakJobMemoryUsed / 1024**3,
        "hard_limit_gib": limits.JobMemoryLimit / 1024**3,
    }


def global_atom_state(kernel):
    """Count shared string atoms without allocating atoms or exporting names."""
    kernel.GlobalGetAtomNameW.argtypes = [W.WORD, W.LPWSTR, C.c_int]
    kernel.GlobalGetAtomNameW.restype = W.UINT
    buffer = C.create_unicode_buffer(256)
    used = sum(bool(kernel.GlobalGetAtomNameW(atom, buffer, len(buffer)))
               for atom in range(0xC000, 0x10000))
    return {"global_atoms_used": used, "global_atom_slots_free": 16384 - used}


def resource_guard_reason(resources, args):
    # Operational reserve, not a Windows guarantee. Keep new capture workloads
    # away from the near-exhausted state that prevented Steam window creation.
    if resources.get("global_atom_slots_free", 16384) < 256:
        return ("global atom reserve below 256 slots "
                f"({resources['global_atom_slots_free']} free); save work and restart Windows")
    limits = (
        ("physical memory", resources["available_physical_gib"], args.min_physical_gib),
        ("page file", resources["available_pagefile_gib"], args.min_pagefile_gib),
        ("disk", resources["free_disk_gib"], args.min_disk_gib),
    )
    for name, available, minimum in limits:
        if available < minimum:
            return f"{name} fell below {minimum:g} GiB ({available:.3f} GiB available)"
    return None


def run(args):
    user, kernel = api()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not Path(command[0]).is_file():
        raise ValueError("Supply an existing absolute executable after --")
    if not Path(command[0]).is_absolute():
        raise ValueError("Executable path must be absolute")
    if not 0 < args.seconds <= 3600:
        raise ValueError("Duration must be between 0 and 3600 seconds")
    report_path = args.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    before = desktop_state(user, kernel)
    desktop_name = "RCRA-Capture-" + uuid.uuid4().hex[:12]
    report = {"desktop": desktop_name, "before": before, "command": command,
              "ui_restrictions": args.ui_restrictions,
              "resource_limits": {
                  "min_physical_gib": args.min_physical_gib,
                  "min_pagefile_gib": args.min_pagefile_gib,
                  "min_disk_gib": args.min_disk_gib,
                  "max_job_memory_gib": args.max_job_memory_gib,
              },
              "priority": args.priority,
              "status": "starting", "started_unix": time.time()}
    desktop = job = None
    process = PROCESS_INFORMATION()
    assigned = False
    try:
        resources = resource_state(kernel, report_path.parent)
        atom_snapshot = global_atom_state(kernel)
        atom_checked_at = time.monotonic()
        resources.update(atom_snapshot)
        report["initial_global_atoms"] = dict(atom_snapshot)
        reason = resource_guard_reason(resources, args)
        report["resources"] = resources
        if reason:
            report.update(status="resource_guard", guard_stage="preflight",
                          resource_guard_reason=reason)
            return
        desktop = check(user.CreateDesktopW(desktop_name, None, None, 0, 0xF01FF, None))
        job = check(kernel.CreateJobObjectW(None, None))
        limits = EXTENDED_LIMIT()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if args.max_job_memory_gib:
            limits.BasicLimitInformation.LimitFlags |= 0x200  # JOB_MEMORY
            limits.JobMemoryLimit = int(args.max_job_memory_gib * 1024**3)
        if args.priority != "normal":
            limits.BasicLimitInformation.LimitFlags |= 0x20  # PRIORITY_CLASS
            limits.BasicLimitInformation.PriorityClass = {
                "below-normal": 0x4000,
                "idle": 0x40,
            }[args.priority]
        check(kernel.SetInformationJobObject(job, 9, C.byref(limits), C.sizeof(limits)))
        if args.ui_restrictions == "desktop-and-display":
            restrictions = W.DWORD(0x40 | 0x10)
            check(kernel.SetInformationJobObject(job, 4, C.byref(restrictions), C.sizeof(restrictions)))
        startup = STARTUPINFO()
        startup.cb = C.sizeof(startup)
        startup.lpDesktop = before["window_station"] + "\\" + desktop_name
        startup.dwFlags = 0x80 | 1  # FORCEOFFFEEDBACK | USESHOWWINDOW
        startup.wShowWindow = 4  # SHOWNOACTIVATE, on the private desktop only
        check(kernel.CreateProcessW(command[0], C.create_unicode_buffer(subprocess.list2cmdline(command)),
                                    None, None, False, 0x4 | 0x400, None,
                                    str(args.cwd.resolve()) if args.cwd else str(Path(command[0]).parent),
                                    C.byref(startup), C.byref(process)))
        check(kernel.AssignProcessToJobObject(job, process.hProcess))
        assigned = True
        resources = resource_state(kernel, report_path.parent)
        atom_snapshot = global_atom_state(kernel)
        atom_checked_at = time.monotonic()
        resources.update(atom_snapshot)
        reason = resource_guard_reason(resources, args)
        report["resources"] = resources
        if reason:
            report.update(status="resource_guard", guard_stage="before_resume",
                          resource_guard_reason=reason)
            return
        if kernel.ResumeThread(process.hThread) == 0xFFFFFFFF:
            raise C.WinError(C.get_last_error())
        report.update(status="running", root_pid=process.dwProcessId,
                      root_thread=process.dwThreadId)
        deadline = time.monotonic() + args.seconds
        while True:
            current = desktop_state(user, kernel)
            if current["input_desktop"] == desktop_name:
                raise RuntimeError("Private desktop unexpectedly became the input desktop")
            members = JOB_PIDS()
            check(kernel.QueryInformationJobObject(job, 3, C.byref(members), C.sizeof(members), None))
            report.update(current=current, job_pids=list(members.pids[:members.count]),
                          windows=windows(user, desktop),
                          resources=resource_state(kernel, report_path.parent),
                          job_memory=job_memory_state(kernel, job),
                          updated_unix=time.time())
            if time.monotonic() - atom_checked_at >= 5:
                atom_snapshot = global_atom_state(kernel)
                atom_checked_at = time.monotonic()
            report["resources"].update(atom_snapshot)
            reason = resource_guard_reason(report["resources"], args)
            if reason:
                report.update(status="resource_guard", guard_stage="running",
                              resource_guard_reason=reason)
                write_report(report_path, report)
                break
            write_report(report_path, report)
            # Direct-editor callers can finish when their root exits. The
            # finally block still terminates every remaining owned helper.
            root_finished = args.exit_with_root and kernel.WaitForSingleObject(process.hProcess, 0) == 0
            if not members.count or root_finished:
                report["helpers_terminated_after_root_exit"] = list(members.pids[:members.count]) if root_finished else []
                report["status"] = "exited"
                exit_code = W.DWORD()
                if kernel.GetExitCodeProcess(process.hProcess, C.byref(exit_code)):
                    report["root_exit_code"] = exit_code.value
                break
            if args.stop_file and args.stop_file.exists():
                report["status"] = "stop_requested"
                break
            if time.monotonic() >= deadline:
                report["status"] = "deadline_reached"
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        report.update(status="interrupted", error="operator interrupted the owned job")
    except Exception as error:
        report.update(status="error", error=str(error))
        raise
    finally:
        if process.hProcess and not assigned:
            kernel.TerminateProcess(process.hProcess, 1)
        if job:
            kernel.TerminateJobObject(job, 0)
            kernel.CloseHandle(job)
        if process.hProcess:
            kernel.WaitForSingleObject(process.hProcess, 5000)
            kernel.CloseHandle(process.hProcess)
        if process.hThread:
            kernel.CloseHandle(process.hThread)
        if desktop:
            user.CloseDesktop(desktop)
        record_final_desktop(report, user, kernel)
        report["finished_unix"] = time.time()
        write_report(report_path, report)
        print(json.dumps({"report": str(report_path), "status": report["status"],
                          "desktop": desktop_name,
                          "input_desktop": report["after"]["input_desktop"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--exit-with-root", action="store_true", help="Stop owned helpers when the direct root process exits; default waits for the whole tree.")
    parser.add_argument("--ui-restrictions", choices=("desktop-and-display", "none"),
                        default="desktop-and-display")
    parser.add_argument("--min-physical-gib", type=float, default=0.0)
    parser.add_argument("--min-pagefile-gib", type=float, default=0.0)
    parser.add_argument("--min-disk-gib", type=float, default=0.0)
    parser.add_argument("--max-job-memory-gib", type=float, default=0.0)
    parser.add_argument("--priority", choices=("normal", "below-normal", "idle"),
                        default="normal")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    run(parser.parse_args())
