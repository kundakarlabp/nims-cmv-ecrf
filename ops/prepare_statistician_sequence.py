#!/usr/bin/env python3
"""Offline, independent-statistician sequence builder (no access to participant data).

Use only after the statistician approves and signs the variable-block sizes,
strata and allocation plan. No real randomization sequence is generated in CI
or committed to Git. Future allocation assignments are never printed.
"""
import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path

STRATA=("rATG:living","rATG:deceased","no_rATG:living","no_rATG:deceased")
RNG=secrets.SystemRandom()

def produce(block_sizes,at_least):
    result=[]
    for stratum in STRATA:
        position=1
        block_no=0
        while position<=at_least:
            block_no+=1
            size=RNG.choice(block_sizes)
            arms=["450"]*(size//2)+["900"]*(size//2)
            RNG.shuffle(arms)
            for arm in arms:
                result.append({"stratum":stratum,"position":position,
                    "block_no":block_no,"block_size":size,"arm":arm})
                position+=1
    return result

def canonical(rows):
    return json.dumps(sorted(rows,key=lambda r:(r["stratum"],r["position"])),
        sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")

def main():
    parser=argparse.ArgumentParser(description="Create independent 1:1 concealed allocation package")
    parser.add_argument("--out",required=True,help="Absolute path on encrypted custodian workstation")
    parser.add_argument("--slots-per-stratum",type=int,default=120)
    parser.add_argument("--block-sizes",default="4,6",help="Only after signed statistician approval")
    parser.add_argument("--statistician-reference",required=True)
    parser.add_argument("--signed-specification-reference",required=True)
    args=parser.parse_args()
    sizes=[int(v.strip()) for v in args.block_sizes.split(",")]
    if len(set(sizes))<2 or any(v not in (4,6,8,10) for v in sizes):
        parser.error("Use at least two distinct signed even block sizes from 4,6,8,10")
    if args.slots_per_stratum<10:parser.error("At least 10 assignments per stratum")
    out=Path(args.out).expanduser().absolute()
    if out.exists():parser.error("Refusing to overwrite an existing signed sequence file")
    if not out.parent.is_dir():parser.error("Create the secure target directory first")
    rows=produce(sizes,args.slots_per_stratum)
    digest=hashlib.sha256(canonical(rows)).hexdigest()
    data={"protocol_version":"5.0",
      "statistician_reference":args.statistician_reference,
      "signed_specification_reference":args.signed_specification_reference,
      "independent_sequence_attested":True,
      "sequence_sha256":digest,"entries":rows}
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY
    descriptor=os.open(str(out),flags,0o600)
    with os.fdopen(descriptor,"w",encoding="utf-8") as output:
        json.dump(data,output,ensure_ascii=True,indent=2)
        output.write("\n")
    print("Sealed-sequence package created on independent workstation.")
    print("SHA-256 of canonical sequence:",digest)
    print("Strata:",", ".join(STRATA))
    print("Positions per stratum:",{k:sum(row["stratum"]==k for row in rows) for k in STRATA})
    print("Store the signed specification and this digest with the independent statistician.")
    print("Do not copy the plaintext assignment file to GitHub, shared Drive or a clinical chat.")

if __name__=="__main__":
    main()
