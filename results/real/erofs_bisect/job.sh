
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
kml_scan
cat $D/kmemleak >> $OUT/kmemleak_boot.txt
echo clear > $D/kmemleak
if [ ! -f $OUT/done_77 ]; then
  for n in $(seq 77 124); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_77.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_77_124.txt; echo clear > $D/kmemleak
  touch $OUT/done_77
fi
if [ ! -f $OUT/done_125 ]; then
  for n in $(seq 125 172); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_125.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_125_172.txt; echo clear > $D/kmemleak
  touch $OUT/done_125
fi
if [ ! -f $OUT/done_173 ]; then
  for n in $(seq 173 220); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_173.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_173_220.txt; echo clear > $D/kmemleak
  touch $OUT/done_173
fi
if [ ! -f $OUT/done_221 ]; then
  for n in $(seq 221 268); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_221.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_221_268.txt; echo clear > $D/kmemleak
  touch $OUT/done_221
fi
if [ ! -f $OUT/done_269 ]; then
  for n in $(seq 269 316); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_269.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_269_316.txt; echo clear > $D/kmemleak
  touch $OUT/done_269
fi
if [ ! -f $OUT/done_317 ]; then
  for n in $(seq 317 364); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_317.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_317_364.txt; echo clear > $D/kmemleak
  touch $OUT/done_317
fi
if [ ! -f $OUT/done_365 ]; then
  for n in $(seq 365 412); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_365.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_365_412.txt; echo clear > $D/kmemleak
  touch $OUT/done_365
fi
if [ ! -f $OUT/done_413 ]; then
  for n in $(seq 413 460); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_413.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_413_460.txt; echo clear > $D/kmemleak
  touch $OUT/done_413
fi
if [ ! -f $OUT/done_461 ]; then
  for n in $(seq 461 508); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_461.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_461_508.txt; echo clear > $D/kmemleak
  touch $OUT/done_461
fi
log done
