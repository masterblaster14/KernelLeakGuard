
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
  for n in $(seq 77 77); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_77.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_77_77.txt; echo clear > $D/kmemleak
  touch $OUT/done_77
fi
if [ ! -f $OUT/done_78 ]; then
  for n in $(seq 78 78); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_78.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_78_78.txt; echo clear > $D/kmemleak
  touch $OUT/done_78
fi
if [ ! -f $OUT/done_79 ]; then
  for n in $(seq 79 79); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_79.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_79_79.txt; echo clear > $D/kmemleak
  touch $OUT/done_79
fi
if [ ! -f $OUT/done_80 ]; then
  for n in $(seq 80 80); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_80.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_80_80.txt; echo clear > $D/kmemleak
  touch $OUT/done_80
fi
if [ ! -f $OUT/done_81 ]; then
  for n in $(seq 81 81); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_81.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_81_81.txt; echo clear > $D/kmemleak
  touch $OUT/done_81
fi
if [ ! -f $OUT/done_82 ]; then
  for n in $(seq 82 82); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_82.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_82_82.txt; echo clear > $D/kmemleak
  touch $OUT/done_82
fi
if [ ! -f $OUT/done_83 ]; then
  for n in $(seq 83 83); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_83.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_83_83.txt; echo clear > $D/kmemleak
  touch $OUT/done_83
fi
if [ ! -f $OUT/done_84 ]; then
  for n in $(seq 84 84); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_84.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_84_84.txt; echo clear > $D/kmemleak
  touch $OUT/done_84
fi
if [ ! -f $OUT/done_85 ]; then
  for n in $(seq 85 85); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_85.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_85_85.txt; echo clear > $D/kmemleak
  touch $OUT/done_85
fi
if [ ! -f $OUT/done_86 ]; then
  for n in $(seq 86 86); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_86.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_86_86.txt; echo clear > $D/kmemleak
  touch $OUT/done_86
fi
if [ ! -f $OUT/done_87 ]; then
  for n in $(seq 87 87); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_87.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_87_87.txt; echo clear > $D/kmemleak
  touch $OUT/done_87
fi
if [ ! -f $OUT/done_88 ]; then
  for n in $(seq 88 88); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_88.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_88_88.txt; echo clear > $D/kmemleak
  touch $OUT/done_88
fi
if [ ! -f $OUT/done_89 ]; then
  for n in $(seq 89 89); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_89.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_89_89.txt; echo clear > $D/kmemleak
  touch $OUT/done_89
fi
if [ ! -f $OUT/done_90 ]; then
  for n in $(seq 90 90); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_90.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_90_90.txt; echo clear > $D/kmemleak
  touch $OUT/done_90
fi
if [ ! -f $OUT/done_91 ]; then
  for n in $(seq 91 91); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_91.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_91_91.txt; echo clear > $D/kmemleak
  touch $OUT/done_91
fi
if [ ! -f $OUT/done_92 ]; then
  for n in $(seq 92 92); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_92.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_92_92.txt; echo clear > $D/kmemleak
  touch $OUT/done_92
fi
if [ ! -f $OUT/done_93 ]; then
  for n in $(seq 93 93); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_93.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_93_93.txt; echo clear > $D/kmemleak
  touch $OUT/done_93
fi
if [ ! -f $OUT/done_94 ]; then
  for n in $(seq 94 94); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_94.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_94_94.txt; echo clear > $D/kmemleak
  touch $OUT/done_94
fi
if [ ! -f $OUT/done_95 ]; then
  for n in $(seq 95 95); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_95.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_95_95.txt; echo clear > $D/kmemleak
  touch $OUT/done_95
fi
if [ ! -f $OUT/done_96 ]; then
  for n in $(seq 96 96); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_96.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_96_96.txt; echo clear > $D/kmemleak
  touch $OUT/done_96
fi
if [ ! -f $OUT/done_97 ]; then
  for n in $(seq 97 97); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_97.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_97_97.txt; echo clear > $D/kmemleak
  touch $OUT/done_97
fi
if [ ! -f $OUT/done_98 ]; then
  for n in $(seq 98 98); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_98.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_98_98.txt; echo clear > $D/kmemleak
  touch $OUT/done_98
fi
if [ ! -f $OUT/done_99 ]; then
  for n in $(seq 99 99); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_99.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_99_99.txt; echo clear > $D/kmemleak
  touch $OUT/done_99
fi
if [ ! -f $OUT/done_100 ]; then
  for n in $(seq 100 100); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_100.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_100_100.txt; echo clear > $D/kmemleak
  touch $OUT/done_100
fi
if [ ! -f $OUT/done_101 ]; then
  for n in $(seq 101 101); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_101.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_101_101.txt; echo clear > $D/kmemleak
  touch $OUT/done_101
fi
if [ ! -f $OUT/done_102 ]; then
  for n in $(seq 102 102); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_102.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_102_102.txt; echo clear > $D/kmemleak
  touch $OUT/done_102
fi
if [ ! -f $OUT/done_103 ]; then
  for n in $(seq 103 103); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_103.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_103_103.txt; echo clear > $D/kmemleak
  touch $OUT/done_103
fi
if [ ! -f $OUT/done_104 ]; then
  for n in $(seq 104 104); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_104.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_104_104.txt; echo clear > $D/kmemleak
  touch $OUT/done_104
fi
if [ ! -f $OUT/done_105 ]; then
  for n in $(seq 105 105); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_105.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_105_105.txt; echo clear > $D/kmemleak
  touch $OUT/done_105
fi
if [ ! -f $OUT/done_106 ]; then
  for n in $(seq 106 106); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_106.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_106_106.txt; echo clear > $D/kmemleak
  touch $OUT/done_106
fi
if [ ! -f $OUT/done_107 ]; then
  for n in $(seq 107 107); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_107.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_107_107.txt; echo clear > $D/kmemleak
  touch $OUT/done_107
fi
if [ ! -f $OUT/done_108 ]; then
  for n in $(seq 108 108); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_108.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_108_108.txt; echo clear > $D/kmemleak
  touch $OUT/done_108
fi
if [ ! -f $OUT/done_109 ]; then
  for n in $(seq 109 109); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_109.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_109_109.txt; echo clear > $D/kmemleak
  touch $OUT/done_109
fi
if [ ! -f $OUT/done_110 ]; then
  for n in $(seq 110 110); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_110.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_110_110.txt; echo clear > $D/kmemleak
  touch $OUT/done_110
fi
if [ ! -f $OUT/done_111 ]; then
  for n in $(seq 111 111); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_111.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_111_111.txt; echo clear > $D/kmemleak
  touch $OUT/done_111
fi
if [ ! -f $OUT/done_112 ]; then
  for n in $(seq 112 112); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_112.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_112_112.txt; echo clear > $D/kmemleak
  touch $OUT/done_112
fi
if [ ! -f $OUT/done_113 ]; then
  for n in $(seq 113 113); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_113.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_113_113.txt; echo clear > $D/kmemleak
  touch $OUT/done_113
fi
if [ ! -f $OUT/done_114 ]; then
  for n in $(seq 114 114); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_114.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_114_114.txt; echo clear > $D/kmemleak
  touch $OUT/done_114
fi
if [ ! -f $OUT/done_115 ]; then
  for n in $(seq 115 115); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_115.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_115_115.txt; echo clear > $D/kmemleak
  touch $OUT/done_115
fi
if [ ! -f $OUT/done_116 ]; then
  for n in $(seq 116 116); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_116.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_116_116.txt; echo clear > $D/kmemleak
  touch $OUT/done_116
fi
if [ ! -f $OUT/done_117 ]; then
  for n in $(seq 117 117); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_117.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_117_117.txt; echo clear > $D/kmemleak
  touch $OUT/done_117
fi
if [ ! -f $OUT/done_118 ]; then
  for n in $(seq 118 118); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_118.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_118_118.txt; echo clear > $D/kmemleak
  touch $OUT/done_118
fi
if [ ! -f $OUT/done_119 ]; then
  for n in $(seq 119 119); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_119.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_119_119.txt; echo clear > $D/kmemleak
  touch $OUT/done_119
fi
if [ ! -f $OUT/done_120 ]; then
  for n in $(seq 120 120); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_120.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_120_120.txt; echo clear > $D/kmemleak
  touch $OUT/done_120
fi
if [ ! -f $OUT/done_121 ]; then
  for n in $(seq 121 121); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_121.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_121_121.txt; echo clear > $D/kmemleak
  touch $OUT/done_121
fi
if [ ! -f $OUT/done_122 ]; then
  for n in $(seq 122 122); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_122.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_122_122.txt; echo clear > $D/kmemleak
  touch $OUT/done_122
fi
if [ ! -f $OUT/done_123 ]; then
  for n in $(seq 123 123); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_123.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_123_123.txt; echo clear > $D/kmemleak
  touch $OUT/done_123
fi
if [ ! -f $OUT/done_124 ]; then
  for n in $(seq 124 124); do klg-agent repeat --mode init --target /mnt/host/mods/erofs.ko --nth $n --count 1 --filter erofs --out $OUT/run_124.log; done
  kml_scan; cat $D/kmemleak > $OUT/kml_124_124.txt; echo clear > $D/kmemleak
  touch $OUT/done_124
fi
log done
