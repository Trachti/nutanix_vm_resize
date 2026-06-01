import http.client
import json
import ssl
import time

NTNX_PRISMCENTRAL_IP = "YOUR_IP:9440"
PC_TOKEN = "YOUR GENERATED TOKEN FROM nutanix_auth.py"


def get_conn(host=NTNX_PRISMCENTRAL_IP):
    context = ssl._create_unverified_context()
    return http.client.HTTPSConnection(host, context=context)


def api_request(method, url, payload=None, host=NTNX_PRISMCENTRAL_IP, token=PC_TOKEN, extra_headers=None):
    conn = get_conn(host)
    headers = {
        "Accept": "application/json",
        "Authorization": token,
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    body = None if payload is None else payload if isinstance(payload, str) else json.dumps(payload)
    conn.request(method, url, body=body, headers=headers)
    res = conn.getresponse()
    raw = res.read().decode("utf-8")
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {"raw": raw}
    if res.status >= 400:
        raise RuntimeError(f"API error {res.status} on {host}{url}: {data}")
    return data, res.status


def task_uuid(response):
    return (response.get("status", {}).get("execution_context", {}).get("task_uuid")
            or response.get("task_uuid")
            or response.get("status", {}).get("task_uuid"))


def wait_for_task(task_id, timeout=300, interval=5):
    start = time.time()
    while time.time() - start < timeout:
        data, _ = api_request("GET", f"/api/nutanix/v3/tasks/{task_id}")
        status = str(data.get("status", "")).upper()
        if status in {"SUCCEEDED", "FAILED", "ABORTED"}:
            return data
        time.sleep(interval)
    raise TimeoutError(f"Task {task_id} reached timeout after {timeout}s.")


def list_vms(page_size=100):
    offset, results = 0, []
    while True:
        payload = {"kind": "vm", "length": page_size, "offset": offset}
        data, _ = api_request("POST", "/api/nutanix/v3/vms/list", payload)
        entities = data.get("entities", [])
        if not entities:
            break
        results.extend(entities)
        total = data.get("metadata", {}).get("total_matches")
        offset += page_size
        if total is not None and offset >= total:
            break
    return results


def get_vm_by_name(name):
    for vm in list_vms():
        if vm.get("spec", {}).get("name") == name:
            return vm
    return None


def get_vm(uuid_):
    data, _ = api_request("GET", f"/api/nutanix/v3/vms/{uuid_}")
    return data


def put_vm(uuid_, vm_data, timeout=300, interval=5):
    response, _ = api_request("PUT", f"/api/nutanix/v3/vms/{uuid_}", vm_data)
    tid = task_uuid(response)
    if tid:
        result = wait_for_task(tid, timeout=timeout, interval=interval)
        if str(result.get("status", "")).upper() != "SUCCEEDED":
            raise RuntimeError(f"Task failed: {result}")
    return get_vm(uuid_)

import argparse


def resolve(name):
    vm = get_vm_by_name(name)
    if not vm:
        raise RuntimeError(f"VM '{name}' was not found.")
    uuid_ = vm["metadata"]["uuid"]
    return uuid_, get_vm(uuid_)


def power_state(vm):
    return vm.get("status", {}).get("resources", {}).get("power_state") or vm.get("spec", {}).get("resources", {}).get("power_state") or "UNKNOWN"


def set_power(uuid_, state):
    vm = get_vm(uuid_)
    vm.pop("status", None)
    vm["spec"]["resources"]["power_state"] = state.upper()
    return put_vm(uuid_, vm)


def find_disk(vm, index):
    for disk in vm.get("spec", {}).get("resources", {}).get("disk_list", []) or []:
        addr = disk.get("device_properties", {}).get("disk_address", {})
        if addr.get("device_index") == index and disk.get("device_properties", {}).get("device_type") == "DISK":
            return disk
    return None


def main():
    parser = argparse.ArgumentParser(description="Resize Nutanix VM CPU, RAM, and disk resources through Prism Central.")
    parser.add_argument("--vm", required=True)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--ram", type=int, help="RAM in GiB")
    parser.add_argument("--disk", type=int, help="Disk size in GiB")
    parser.add_argument("--disk-index", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--power-off-if-needed", action="store_true")
    parser.add_argument("--power-on-after", action="store_true")
    args = parser.parse_args()
    if args.cpu is None and args.ram is None and args.disk is None:
        raise ValueError("At least one of --cpu, --ram, or --disk is required.")
    uuid_, vm = resolve(args.vm)
    print(f"VM: {args.vm}\nUUID: {uuid_}\nCurrent power state: {power_state(vm)}")
    if args.dry_run:
        print("Dry-run mode. No changes were applied.")
        return
    if not args.force:
        raise RuntimeError("Applying changes requires --force.")
    if power_state(vm).upper() == "ON" and args.power_off_if_needed:
        vm = set_power(uuid_, "OFF")
    vm.pop("status", None)
    res = vm["spec"]["resources"]
    if args.cpu is not None:
        res["num_sockets"] = 1
        res["num_vcpus_per_socket"] = args.cpu
    if args.ram is not None:
        res["memory_size_mib"] = args.ram * 1024
    if args.disk is not None:
        disk = find_disk(vm, args.disk_index)
        if not disk:
            raise RuntimeError(f"Disk with index {args.disk_index} was not found.")
        new_size = args.disk * 1024
        if disk.get("disk_size_mib") and new_size < disk["disk_size_mib"]:
            raise RuntimeError("Disk shrinking is not supported.")
        disk["disk_size_mib"] = new_size
    updated = put_vm(uuid_, vm)
    if args.power_on_after:
        updated = set_power(uuid_, "ON")
    print(f"Resize completed. Power state: {power_state(updated)}")

if __name__ == "__main__":
    main()
