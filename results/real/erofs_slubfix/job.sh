
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
if [ -f $OUT/started_77 ] && [ ! -f $OUT/done_77 ]; then echo crashed > $OUT/crashed_77; touch $OUT/done_77; fi
if [ ! -f $OUT/done_77 ]; then
  touch $OUT/started_77
  for n in $(seq 77 124); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_77.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_77_124.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_77.txt
  touch $OUT/done_77
fi
if [ -f $OUT/started_125 ] && [ ! -f $OUT/done_125 ]; then echo crashed > $OUT/crashed_125; touch $OUT/done_125; fi
if [ ! -f $OUT/done_125 ]; then
  touch $OUT/started_125
  for n in $(seq 125 172); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_125.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_125_172.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_125.txt
  touch $OUT/done_125
fi
if [ -f $OUT/started_173 ] && [ ! -f $OUT/done_173 ]; then echo crashed > $OUT/crashed_173; touch $OUT/done_173; fi
if [ ! -f $OUT/done_173 ]; then
  touch $OUT/started_173
  for n in $(seq 173 220); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_173.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_173_220.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_173.txt
  touch $OUT/done_173
fi
if [ -f $OUT/started_221 ] && [ ! -f $OUT/done_221 ]; then echo crashed > $OUT/crashed_221; touch $OUT/done_221; fi
if [ ! -f $OUT/done_221 ]; then
  touch $OUT/started_221
  for n in $(seq 221 268); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_221.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_221_268.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_221.txt
  touch $OUT/done_221
fi
if [ -f $OUT/started_269 ] && [ ! -f $OUT/done_269 ]; then echo crashed > $OUT/crashed_269; touch $OUT/done_269; fi
if [ ! -f $OUT/done_269 ]; then
  touch $OUT/started_269
  for n in $(seq 269 316); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_269.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_269_316.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_269.txt
  touch $OUT/done_269
fi
if [ -f $OUT/started_317 ] && [ ! -f $OUT/done_317 ]; then echo crashed > $OUT/crashed_317; touch $OUT/done_317; fi
if [ ! -f $OUT/done_317 ]; then
  touch $OUT/started_317
  for n in $(seq 317 364); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_317.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_317_364.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_317.txt
  touch $OUT/done_317
fi
if [ -f $OUT/started_365 ] && [ ! -f $OUT/done_365 ]; then echo crashed > $OUT/crashed_365; touch $OUT/done_365; fi
if [ ! -f $OUT/done_365 ]; then
  touch $OUT/started_365
  for n in $(seq 365 412); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_365.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_365_412.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_365.txt
  touch $OUT/done_365
fi
if [ -f $OUT/started_413 ] && [ ! -f $OUT/done_413 ]; then echo crashed > $OUT/crashed_413; touch $OUT/done_413; fi
if [ ! -f $OUT/done_413 ]; then
  touch $OUT/started_413
  for n in $(seq 413 460); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_413.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_413_460.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_413.txt
  touch $OUT/done_413
fi
if [ -f $OUT/started_461 ] && [ ! -f $OUT/done_461 ]; then echo crashed > $OUT/crashed_461; touch $OUT/done_461; fi
if [ ! -f $OUT/done_461 ]; then
  touch $OUT/started_461
  for n in $(seq 461 508); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_461.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_461_508.txt; echo clear > $D/kmemleak
  dmesg > $OUT/dmesg_461.txt
  touch $OUT/done_461
fi
log done
