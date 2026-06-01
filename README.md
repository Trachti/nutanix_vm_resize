# Nutanix VM Resize Script

Resize Nutanix VM CPU, RAM, and disk resources through Prism Central.

## Features

- Resize CPU
- Resize RAM in GiB
- Expand disk size
- Prevents disk shrinking
- Supports dry-run mode
- Requires `--force` to apply changes
- Can power off before resize and power on afterwards

## Configuration

Edit `nutanix_vm_resize.py`:

```python
NTNX_PRISMCENTRAL_IP = "YOUR_IP:9440"
PC_TOKEN = "YOUR GENERATED TOKEN FROM nutanix_auth.py"
```

## Usage

```bash
python nutanix_vm_resize.py --vm server01 --cpu 4 --ram 16 --dry-run
python nutanix_vm_resize.py --vm server01 --cpu 4 --ram 16 --force
python nutanix_vm_resize.py --vm server01 --disk 120 --disk-index 0 --force
python nutanix_vm_resize.py --vm server01 --cpu 4 --ram 16 --power-off-if-needed --power-on-after --force
```

## Safety Notes

Use `--dry-run` first. Disk shrinking is not supported. Do not commit real tokens or infrastructure details.

## Disclaimer

Example script. Test in a safe environment before production use.
