#include <tunables/global>

profile tbe-bot flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  #include <abstractions/python>

  network inet stream,
  network inet dgram,
  network inet6 stream,
  network inet6 dgram,

  /app/** r,
  /app/**/__pycache__/ rw,
  /tmp/** rw,
  /var/tmp/** rw,
  /run/secrets/** r,
  /etc/ssl/** r,
  /etc/passwd r,
  /etc/nsswitch.conf r,
  /etc/resolv.conf r,
  /etc/hosts r,
  /usr/lib/** mr,
  /usr/local/lib/** mr,
  /lib/** mr,
  /proc/*/status r,
  /proc/sys/kernel/ngroups_max r,
  /sys/devices/system/cpu/online r,

  deny /var/run/docker.sock rwklx,
  deny /run/docker.sock rwklx,
  deny capability sys_admin,
  deny capability sys_module,
  deny capability sys_rawio,
  deny capability mac_admin,
  deny capability mac_override,
  deny mount,
  deny pivot_root,
  deny ptrace,
  deny reboot,
}
