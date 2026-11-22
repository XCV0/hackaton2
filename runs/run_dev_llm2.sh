#!/bin/sh
cd /Users/artemshelkunov/hackaton2
P=".venv/bin/python -u -m backend.cli process"
$P --domain rag --split dev --pub D006 D007 D008 D009 D021 > runs/dev2_1.log 2>&1 &
$P --domain rag --split dev --pub D013 D014 D015 D016 D017 > runs/dev2_2.log 2>&1 &
$P --domain solar --split dev --pub D005 D006 D008 D009 D010 D012 D013 D014 > runs/dev2_3.log 2>&1 &
$P --domain solar --split dev --pub D015 D016 D017 D018 D019 D020 D021 D022 > runs/dev2_4.log 2>&1 &
wait
echo ALLDONE >> runs/dev2_1.log
