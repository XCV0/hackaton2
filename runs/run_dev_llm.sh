#!/bin/sh
cd /Users/artemshelkunov/hackaton2
P=".venv/bin/python -m backend.cli process"
$P --domain rag --split dev --pub D003 D004 D005 D006 D007 D008 D009 > runs/dev_llm_1.log 2>&1 &
$P --domain rag --split dev --pub D010 D011 D012 D013 D014 D015 D016 D017 > runs/dev_llm_2.log 2>&1 &
$P --domain rag --split dev --pub D018 D019 D020 D021 > runs/dev_llm_3.log 2>&1 &
$P --domain solar --split dev --pub D002 D003 D006 D007 D008 D009 D010 D012 D013 D014 D015 D016 D017 D018 D019 D020 D021 D022 > runs/dev_llm_4.log 2>&1 &
wait
echo ALLDONE >> runs/dev_llm_1.log
