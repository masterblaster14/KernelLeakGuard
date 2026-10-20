
D=/sys/kernel/debug
OUT=/mnt/host/out
export D OUT
log() { echo "[job $(cut -d' ' -f1 /proc/uptime)] $*"; }
kml_scan() { sleep 6; echo scan > $D/kmemleak; echo scan > $D/kmemleak; }
# next_n LOG: fault number to resume a sweep at (after a crash: skip the
# attempt that was running when the guest died).
next_n() { [ -f "$1" ] || { echo 1; return; }
  n=$(grep -o '^@@BEGIN n=[0-9]*' "$1" | tail -1 | cut -d= -f2); echo $(( ${n:-0} + 1 )); }

insmod /mnt/host/mods/klg_modwatch.ko || log 'insmod klg_modwatch failed'
insmod /mnt/host/mods/configfs.ko || log 'insmod configfs failed'
kml_scan
cat $D/kmemleak >> $OUT/kmemleak_boot.txt
echo clear > $D/kmemleak
if [ -f $OUT/started_739 ] && [ ! -f $OUT/done_739 ]; then echo crashed > $OUT/crashed_739; touch $OUT/done_739; fi
if [ ! -f $OUT/done_739 ]; then
  touch $OUT/started_739
  for n in $(seq 739 739); do klg-agent repeat --mode init --target /mnt/host/mods/null_blk.ko --nth $n --count 1 --filter null_blk --out $OUT/run_739.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_739_739.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_739.txt
  touch $OUT/done_739
fi
log done
