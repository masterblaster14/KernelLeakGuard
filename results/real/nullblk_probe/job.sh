
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
if [ ! -f $OUT/done_739 ]; then
  for n in $(seq 739 739); do klg-agent repeat --mode init --target /mnt/host/mods/null_blk.ko --nth $n --count 1 --filter null_blk --out $OUT/run_739.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_739_739.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_739.txt
  touch $OUT/done_739
fi
if [ ! -f $OUT/done_740 ]; then
  for n in $(seq 740 740); do klg-agent repeat --mode init --target /mnt/host/mods/null_blk.ko --nth $n --count 1 --filter null_blk --out $OUT/run_740.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_740_740.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_740.txt
  touch $OUT/done_740
fi
if [ ! -f $OUT/done_741 ]; then
  for n in $(seq 741 741); do klg-agent repeat --mode init --target /mnt/host/mods/null_blk.ko --nth $n --count 1 --filter null_blk --out $OUT/run_741.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_741_741.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_741.txt
  touch $OUT/done_741
fi
if [ ! -f $OUT/done_742 ]; then
  for n in $(seq 742 742); do klg-agent repeat --mode init --target /mnt/host/mods/null_blk.ko --nth $n --count 1 --filter null_blk --out $OUT/run_742.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_742_742.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_742.txt
  touch $OUT/done_742
fi
if [ ! -f $OUT/done_743 ]; then
  for n in $(seq 743 743); do klg-agent repeat --mode init --target /mnt/host/mods/null_blk.ko --nth $n --count 1 --filter null_blk --out $OUT/run_743.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_743_743.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_743.txt
  touch $OUT/done_743
fi
if [ ! -f $OUT/done_744 ]; then
  for n in $(seq 744 744); do klg-agent repeat --mode init --target /mnt/host/mods/null_blk.ko --nth $n --count 1 --filter null_blk --out $OUT/run_744.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_744_744.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_744.txt
  touch $OUT/done_744
fi
if [ ! -f $OUT/done_745 ]; then
  for n in $(seq 745 745); do klg-agent repeat --mode init --target /mnt/host/mods/null_blk.ko --nth $n --count 1 --filter null_blk --out $OUT/run_745.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_745_745.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_745.txt
  touch $OUT/done_745
fi
if [ ! -f $OUT/done_746 ]; then
  for n in $(seq 746 746); do klg-agent repeat --mode init --target /mnt/host/mods/null_blk.ko --nth $n --count 1 --filter null_blk --out $OUT/run_746.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_746_746.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_746.txt
  touch $OUT/done_746
fi
log done
