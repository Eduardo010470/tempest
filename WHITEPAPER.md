# Tempest

**A proof-of-work blockchain written from scratch, and what it costs to break it**

Technical specification · Version 1.0 · November 2026

---

## Abstract

Tempest is a proof-of-work blockchain implemented in approximately 3,100 lines
of Python with no external dependencies. The elliptic curve, the signature
scheme, the Merkle tree, the mnemonic derivation and the secret-sharing scheme
are all written out by hand, from their published specifications, and each is
checked against an independent reference: the signature against the 19 official
BIP-340 test vectors, the mnemonic against the Trezor reference implementation
across 300 random phrases.

This document specifies the protocol exactly as implemented. It is a
specification, not a proposal. Every number in it can be checked against the
source, and Section 13 lists the commands that check them.

Tempest issues a token called TEMP. TEMP has no price, no market, and no
mechanism by which it could acquire one. This is stated here rather than
omitted, because a system whose documentation is honest about what it is not
is easier to trust about what it is.

---

## 1. Scope

### 1.1 What this system does

Tempest maintains a single ordered ledger of value transfers, replicated across
independent nodes that trust neither each other nor any third party. Each node
derives the full state from the genesis block using only rules written in its
own source code. No node accepts a balance, a difficulty, a timestamp or a
block from any other node without recomputing it.

### 1.2 What this system does not do

The following are absent by design, not by oversight:

- **Scripts or contracts.** A transaction transfers value and nothing else.
- **Key derivation trees.** One seed phrase yields exactly one key (§9).
- **Privacy.** Addresses are public and linkable, as in Bitcoin.
- **Light clients.** Merkle inclusion proofs exist (§5.3) but no client
  consumes them.
- **Interoperability.** Tempest cannot hold, wrap or reference assets of other
  chains. A transaction has no field in which such a claim could be written,
  and no Tempest node can alter another chain's ledger.

Section 12 lists the limitations that *are* defects rather than scope choices.

---

## 2. Keys and addresses

### 2.1 Curve

Tempest uses secp256k1, the curve defined in SEC 2 and used by Bitcoin:

```
p = 2^256 − 2^32 − 977
n = FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFE BAAEDCE6 AF48A03B BFD25E8C D0364141
G = (79BE667E F9DCBBAC 55A06295 CE870B07 029BFCDB 2DCE28D9 59F2815B 16F81798,
     483ADA77 26A3C465 5DA4FBFC 0E1108A8 FD17B448 A6855419 9C47D08F FB10D4B8)
```

Point addition and scalar multiplication are implemented directly in
`curva.py`: affine coordinates, double-and-add, modular inverse by Fermat's
little theorem. There is no constant-time guarantee; see §12.9.

### 2.2 Public keys

A public key is **32 bytes**: the x-coordinate only, big-endian, with the even
y-coordinate implied. This is the BIP-340 convention. A verifier recovers the
point by solving `y² = x³ + 7 (mod p)` and taking the root with even parity,
which is cheap because `p ≡ 3 (mod 4)`:

```
y = (x³ + 7)^((p+1)/4)  mod p
```

If `y² ≠ x³ + 7`, the x-coordinate is not on the curve and the key is rejected.

Half the key size is saved and no information is lost, because the two
candidate y values are negatives of each other and the convention fixes which
one is meant.

### 2.3 Addresses

```
address = sha256(public_key)[0:20]
```

expressed as 40 lowercase hexadecimal characters. There is no checksum, no
version byte and no base58 encoding; §12.4 treats this as a defect.

An address is generated offline. No registry is consulted and no party is
asked for permission. The address of a key that has never been online is as
valid as any other, and can receive value before its owner has ever connected
to anything.

---

## 3. Transactions

### 3.1 Fields

A transaction is a JSON object with seven fields:

| Field | Type | Meaning |
|---|---|---|
| `de` | 64 hex chars, or `null` | sender's public key; `null` marks a coinbase |
| `para` | 40 hex chars | recipient address |
| `valor` | integer ≥ 1 | amount transferred |
| `taxa` | integer ≥ 0 | fee, paid to whoever mines the block |
| `seq` | integer ≥ 0, or `null` | sender's sequence number; `null` for coinbase |
| `quando` | integer | Unix seconds, as claimed by the signer |
| `assinatura` | 128 hex chars, or `null` | BIP-340 signature over §3.2 |

### 3.2 The signed bytes

The signature covers exactly **84 bytes**, fixed width, big-endian:

```
public key    32 bytes
recipient     20 bytes
value          8 bytes
fee            8 bytes
sequence       8 bytes
timestamp      8 bytes
             ─────────
              84 bytes
```

This encoding is not JSON, and that is deliberate. While the signed form was
produced by a language's serializer, the identity of a transaction depended on
how that serializer chose to write a number — how many decimal places a float
received, whether keys were sorted, how whitespace was placed. Two honest
implementations in two languages would have computed different hashes for the
same transaction and rejected each other's blocks, with no party at fault.
Fixed-width big-endian integers mean the same thing on every machine that can
count.

The timestamp is an integer number of seconds, never a float, for the same
reason.

### 3.3 Transaction identifier

```
txid = sha256(type_byte || ...)
```

where the first byte distinguishes the two kinds so that no coinbase can ever
collide with a signed transfer:

```
signed  : 0x01 || signed_bytes(84) || signature(64)   = 149 bytes
coinbase: 0x00 || recipient(20) || value(8) || time(8) =  37 bytes
```

### 3.4 Signatures

Tempest signs with Schnorr as specified in **BIP-340**. All tagged hashes use

```
H_tag(m) = sha256( sha256(tag) || sha256(tag) || m )
```

with the tags `BIP0340/aux`, `BIP0340/nonce` and `BIP0340/challenge`. The
nonce is derived deterministically from the private key, the auxiliary
randomness and the message, so two different messages never reuse a nonce by
accident — a failure mode that has cost real money on other systems.

A signature is 64 bytes: `R.x || s`. Verification checks that

```
s·G = R + e·P      where e = H_challenge(R.x || P.x || m) mod n
```

with `R` reconstructed by lifting `R.x` to the even-y point, and with the
rejections required by the specification: `r ≥ p`, `s ≥ n`, an x-coordinate not
on the curve, or a reconstructed `R` with odd y or at infinity.

`schnorr.py vetores` runs all 19 official BIP-340 vectors, including the twelve
that must **fail**. Those are the interesting half: an implementation that only
accepts what it should accept has not been tested.

### 3.5 Validity of a transaction in isolation

A transaction is rejected unless all of the following hold:

1. `de` is not `null` (coinbases are validated separately, §6.6).
2. `valor ≥ 1` and `taxa ≥ 0`.
3. `seq` is an integer and `seq ≥ 0`.
4. the public key is exactly 32 bytes.
5. the sender's address differs from `para` (no self-transfer).
6. the BIP-340 signature verifies over the 84 bytes of §3.2.

These are necessary, not sufficient. Sequence and balance are checked against
chain state in §6.5.

---

## 4. Replay protection

A signature is eternal. Anyone who observed a transaction can store it and
resubmit it later; nothing about the cryptography prevents this, and the
signature will still verify.

Tempest carries the sender's **sequence number** inside the signed bytes. For
an address, the expected sequence is the count of transactions that address has
already sent in the chain. A transaction is accepted only when its `seq` equals
that count exactly, and the count then increments. A resubmitted transaction
arrives carrying a number already spent and is rejected.

The lesson generalises: **a valid signature is not an authorisation.**
Authorisation is a valid signature *plus* a state that still accepts it.
Bitcoin solves the same problem with UTXOs; Ethereum solves it with a per-
account nonce, which is the approach taken here.

`cadeia.py repetir` performs the attack: it returns a confirmed, untampered,
correctly signed transaction to the pending queue, and the next miner discards
it.

---

## 5. Blocks

### 5.1 Header

The proof of work covers exactly **88 bytes**, fixed width, big-endian:

```
index          8 bytes
previous hash 32 bytes
merkle root   32 bytes
timestamp      8 bytes
nonce          8 bytes
             ─────────
              88 bytes
```

```
block_hash = sha256(header_bytes)
```

Because the header is raw bytes rather than serialised JSON, the hash can be
reproduced outside Python — with `sha256sum` over the 88 bytes, for example.
§13 gives the command.

Transactions are not in the header. They enter through the Merkle root, which
is what makes a 88-byte proof of work bind an arbitrarily large block.

### 5.2 Merkle root

Transaction identifiers are the leaves. Each level is reduced pairwise until
one hash remains. When a level has an odd number of nodes, the last node is
duplicated.

For an empty transaction list the root is `sha256("")`:

```
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

**Note on the concatenation.** Tempest concatenates the *hexadecimal strings*
of two child hashes and hashes the resulting 128 ASCII characters as UTF-8.
Bitcoin concatenates the 32 raw bytes of each child and applies sha256 twice.
Tempest's choice doubles the hashed input and is not interoperable with
Bitcoin's. It is recorded here because a specification that differs silently
from the thing it resembles is worse than no specification.

### 5.3 Inclusion proofs

To prove that transaction *n* is in a block, it suffices to publish the sibling
hashes along its path to the root — ⌈log₂ N⌉ hashes, each tagged with the side
it joins on. The verifier recomputes the path upward and compares with the root
in the header, having never seen the other transactions.

`cadeia.py prova <block> <n>` emits such a proof. This is the mechanism a light
client would consume; no such client exists here (§1.2).

### 5.4 Proof of work

A block is valid only if its hash, in hexadecimal, begins with *d* zero
characters, where *d* is the difficulty required for its height (§7). One hex
character is four bits, so *d* leading zeros is 4*d* leading zero bits, and each
additional zero multiplies the expected number of attempts by sixteen.

Mining is the search for a nonce satisfying this. The nonce is 8 bytes; the
timestamp is not modified during the search, except to satisfy the median floor
at the start (§8).

---

## 6. Chain validation

A node derives everything from the genesis block and its own source. The checks
below are applied in this order; the first failure rejects the chain.

### 6.1 Genesis

The genesis block is a **constant in the source code**, not a block mined at
installation time:

```python
GENESE = {
    "indice":      0,
    "anterior":    "4b21ebff52639c9be4e81a54c99e17beb900b626e86bb482be1c06016b5d02b4",
    "raiz":        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "quando":      1793577600,
    "nonce":       42837,
    "transacoes":  [],
    "hash":        "0000d4fd8d4447688c6088930c5ed25c3eea7cba7098f2f470115a7da9239492",
}
```

`anterior` holds `sha256("Tempest")`, there being no earlier block to point to.
Satoshi used that space for the headline of *The Times* of 3 January 2009.
`quando` is 2026-11-02T00:00:00Z. The nonce was mined once and never again.

Validation compares the genesis **field by field** against this constant —
index, previous hash, Merkle root, timestamp, nonce and hash — and requires
that it contain no transactions. A chain whose genesis differs in any field is
a chain of a different network and is rejected however much work it carries.

This matters more than it appears. An earlier revision of this software mined
its genesis at install time, so two installations were born with different
origins. The consequence was not a visible split: validation checked only the
`anterior` field, so the node with more work imposed its genesis on the other,
which silently lost every block it had mined. **A network is not defined by
whoever arrives with the most work. It is defined by a common origin.**

### 6.2 Structure, per block

- `indice` equals the block's position in the chain.
- the Merkle root in the header equals the root recomputed from the block's
  transaction list.
- `hash` equals `sha256` of the 88 header bytes.
- the hash meets the difficulty required at that height (§7).

### 6.3 Linkage, for every block after genesis

- `anterior` equals the hash of the preceding block.

### 6.4 Time, for every block after genesis

- `quando` is strictly greater than the median of the previous 11 timestamps.
- `quando` is at most 30 seconds ahead of the validating node's clock.

See §8.

### 6.5 Transactions, in order

The validator carries running balances and sequence counts, starting empty, and
for each transaction in each block:

- at most one coinbase per block;
- every non-coinbase transaction satisfies §3.5;
- `seq` equals the sender's current count, exactly;
- the sender's balance is at least `valor + taxa`;
- then: balance debited by `valor + taxa`, recipient credited `valor`,
  sequence incremented, fee accumulated.

Note that the sender is debited the fee but no one is credited it here; the fee
is paid out through the coinbase.

### 6.6 Coinbase

Let `fees` be the sum of fees in the block and `reward(i)` the issuance at that
height (§10). Then:

- if a coinbase is present, its `valor` must equal `reward(i) + fees` exactly —
  not less, not more;
- if no coinbase is present and `reward(i) + fees > 0`, the block is invalid.

A miner cannot pay itself a round number, cannot forget the fees and cannot
invent a coin.

---

## 7. Difficulty

Difficulty is a property of the chain, not an instruction carried in it. Every
node computes it from the past alone and arrives at the same number. There is
no authority announcing it.

```
d = 4                            # DIF_INICIAL
for each multiple m of 10 with m ≤ height:
    elapsed  = chain[m-1].time − chain[m-10].time
    expected = 5 × (10 − 1) = 45 seconds
    if elapsed < expected / 2  and d < 7:  d += 1
    if elapsed > expected × 2  and d > 3:  d -= 1
```

Difficulty is clamped to the range [3, 7]. Blocks target 5 seconds apart and
the window is 10 blocks. These values are small so that a reader can watch a
retarget happen in under a minute; §12.14 notes the consequence.

**Accumulated work** is the sum over all blocks of `16^d`, where `d` is the
difficulty required at that height. This, not block count, is the quantity
compared when two chains disagree (§11.1). A six-zero block cost sixteen times a
five-zero block, and a chain of fewer, harder blocks can outweigh a longer one.

---

## 8. Timestamps

Difficulty is computed from timestamps, and timestamps are written by the
miners themselves. Without constraint, a miner could date a block in the past,
make the window appear long, push the difficulty down and mine cheaply.

Two bounds apply:

- **Floor.** A block's timestamp must exceed the median of the previous eleven.
  A single lying block cannot move a median of eleven; to move it, an attacker
  must already control most of the network, at which point it has worse things
  to do to us. This is Bitcoin's median-time-past rule.
- **Ceiling.** A block more than 30 seconds ahead of the validator's clock is
  rejected.

`cadeia.py atrasar` performs the attack honestly: it mines a **real** block,
spending the full proof of work, with correct linkage, legitimate transactions
and a matching Merkle root. The only false thing is the hour. The block is
rejected, and nothing is written to disk — the attack is assembled in memory
and submitted to validation, exactly as a node would treat a stranger's block.

**This defence limits the attack; it does not eliminate it.** Between the
median floor and the future ceiling there remains slack, and whoever holds a
majority moves the median. Bitcoin carries the same residual weakness — the
time-warp attack, known and demonstrated on its testnet. No one has removed it
for free; what is done is to make the slack too small to be worth the trouble.

---

## 9. Key backup

### 9.1 Mnemonic

A private key is a 256-bit number. Losing the file that holds it loses the
coins, with no recovery and no support desk, and a number of that size cannot
be copied by hand without error.

Tempest implements **BIP-39** as published: 128 bits of entropy plus a 4-bit
checksum, split into twelve groups of 11 bits, each indexing a 2,048-word list.
The four check bits are the clever part: a single miscopied word fails the
checksum and the program says so, instead of handing back a silent empty
wallet. The first four letters of every word in the list are already unique, so
four letters per word is a sufficient backup.

The word list is the official Portuguese one from the BIPs repository,
`md5 05ee6fde129776830351bbacd5b0dcfb`, identical in the `bitcoin/bips` and
`trezor/python-mnemonic` repositories.

Phrase to seed is BIP-39 exactly:

```
seed = PBKDF2-HMAC-SHA512( normalise(phrase), "mnemonic" + passphrase, 2048, 64 )
```

The 2,048 rounds exist to make brute-forcing the phrase expensive.

### 9.2 Seed to key

Real wallets continue from here into BIP-32, deriving an infinite tree of keys,
which is why they produce a fresh address for every receipt. **Tempest does
not.** It takes the first step and stops:

```
k = int( HMAC-SHA512( key = "Tempest seed", msg = seed )[0:32] ) mod n
```

One seed, one key. Backup works identically; the privacy of many addresses is
not implemented. The HMAC key string differs from BIP-32's `"Bitcoin seed"`, so
a Tempest phrase and a Bitcoin phrase with the same words yield unrelated keys.

The implementation is checked against `trezor/python-mnemonic` over 300 random
phrases, at every entropy size, with and without a passphrase: phrase and seed
identical in every case.

### 9.3 Splitting the seed

`partilha.py` implements Shamir's secret sharing over the prime field

```
P = 2^128 + 51
```

the smallest prime above the 128 bits of entropy in the phrase. The secret
becomes the constant term of a polynomial of degree *k*−1; the shares are points
on it. Any *k* points determine the polynomial by Lagrange interpolation at
*x* = 0; any *k*−1 determine nothing.

"Nothing" is literal, not approximate. With *k*−1 shares, for **every** possible
secret there exists exactly one polynomial passing through those points with
that secret — all equally consistent. The deficiency is not computational
power; it is information. This is Shannon-perfect secrecy, and
`partilha.py provar` demonstrates it with numbers.

Shares are written to files with mode 600 and are never printed to the screen.

---

## 10. Issuance

```
reward(i) = 50 >> (i // 20)
```

| | |
|---|---|
| Target block interval | 5 seconds |
| Difficulty retarget | every 10 blocks |
| Initial reward | 50 TEMP |
| Halving | every 20 blocks |
| Last block with a reward | 119 (reward: 1 TEMP) |
| Total ever issued | 1,890 TEMP (see below) |
| Fee | set by the sender, paid to the miner |

The genesis block contains no transactions and therefore issues nothing; the
total above sums heights 1 through 119.

**That total is a rounding artifact.** The geometric sum of 50 halving every
20 blocks is 50 × 20 × 2 = 2,000, less the 50 of the non-issuing genesis:
**1,950 TEMP**. The chain creates 1,890. The missing 60 — 3.1% of the intended
supply — were eaten by integer truncation, because `50 >> 2` yields 12 where
the curve calls for 12.5, and so on at every halving. See §12.15.

These numbers are small on purpose: a reader sees a halving in minutes and the
end of issuance in an afternoon. In Bitcoin the halving is every four years and
issuance ends in 2140 — the same curve on a scale no one lives to watch whole.

After block 119 the reward is zero and **fees alone** pay for mining. This is
the long-run problem of every capped currency, and here it arrives quickly
enough to be observed rather than argued about.

---

## 11. The network

### 11.1 Consensus between nodes

With one node, whoever writes the chain owns it. The interesting problem begins
with two, because they can disagree and there is no referee. The rule that
settles it:

> **the valid chain with the most accumulated work wins**

Both conditions are required and they are checked in that order: a chain with
more work that fails validation is rejected, and a valid chain with less work is
not adopted. A node adopting a foreign chain re-derives every balance, every
signature, every Merkle root, every difficulty and the genesis itself. Adoption
is the end of an audit, not an act of deference.

Note what the rule implies: whoever holds more computing power than everyone
else combined writes the history. The security does not come from the
cryptography. It comes from that power being too expensive to assemble.

### 11.2 Reorganisation

When a foreign chain wins, the discarded blocks carried transactions, and those
cannot simply evaporate. They are collected before the swap, and afterwards
they are judged against the **new** chain: those the new chain already confirmed
by another path are rejected as replays; the rest return to the pending queue
and compete for a place in future blocks.

This is where the practical rule about waiting for confirmations comes from. A
transaction is not settled because it is in a block; it is settled when undoing
the block that holds it has become too expensive. Those are different
statements.

### 11.3 Wire protocol

HTTP with JSON bodies.

| Method | Route | Meaning |
|---|---|---|
| GET | `/estado` | height, accumulated work, validity, tip hash, peer count |
| GET | `/cadeia` | the full chain |
| GET | `/pendentes` | the pending queue |
| GET | `/pares` | this node's identity and peer list |
| POST | `/cadeia` | offer a chain; the node applies §11.1 |
| POST | `/pendentes` | offer transactions; the node applies §11.4 |
| POST | `/pares` | exchange peer lists |

A POST body larger than 8 MiB is refused with 413 before being read, so that a
false `Content-Length` cannot exhaust memory.

No route on the network-facing node touches a private key. The browser wallet
(`tela.py`), which does sign and does mine to the operator's address, binds to
`127.0.0.1` and refuses any client that is not the machine itself.

### 11.4 Transaction relay

An offered transaction is dropped when it is already held, when its signature
fails, or when its sequence is below the sender's confirmed count. The third
filter is the important one: a transaction may be perfectly signed and still be
a replay of something the chain has already confirmed. Rejecting it at the door
means it dies before entering the queue and is never relayed onward.

### 11.5 Peer discovery

A node keeps a list of the peers it knows and exchanges that list with everyone
it meets. Introduce it to **one** peer and it finds the rest. Three nodes, with
the third introduced only to the second, and the third learns the first on its
opening exchange. That is all "decentralised" means in practice.

### 11.6 Seed nodes

A freshly installed node knows no one, and there is no way for it to discover
on its own who is running. So the list starts written into the source, in
`PARES_SEMENTE`. **This is the one part of a blockchain that is not
mathematics:** an address that somebody must keep standing. Bitcoin has five of
them — the DNS seeds — and has never managed to remove any.

Observe what a seed node *cannot* do. It cannot lie about the chain, because
the genesis is a constant and validation is complete; a false history is
rejected however much work it carries. It cannot invent peers, because the ones
it names either present themselves or are never spoken to. It cannot spend
anyone's coins, because it holds no key. The worst a seed node can do is fail
to answer.

It also needs no backup. A seed node's disk is expendable: on restart it reads
its seed list, requests the chain from its peers, and validation decides. This
is what the constant genesis bought, and it is only visible here.

---

## 12. Known limitations

Scope choices are in §1.2. These are weaknesses.

1. **One seed node, one operator.** The network has a single entry point, run
   by one person on a free hosting tier. A real network has several, on
   different machines in different jurisdictions, none of them indispensable.
2. **Full-chain transfer.** Synchronisation downloads the entire chain as JSON.
   There is no headers-first sync, no block range request and no compression.
   Transfer is O(n) in chain length for every sync.
3. **Quadratic validation.** `valida` calls the difficulty function per block,
   and that function rescans the chain, making full validation O(n²). Acceptable
   for a chain of hundreds of blocks; not for one of millions.
4. **No address checksum.** A mistyped address is a valid address. Coins sent
   there are visible forever and unreachable forever. Bitcoin's base58check and
   bech32 exist precisely to make this impossible.
5. **Merkle duplication.** Duplicating the final node on odd levels means two
   different transaction lists can produce the same root — the structure behind
   Bitcoin's CVE-2012-2459. Here the sequence and balance rules reject the
   duplicate list for other reasons, so the weakness is masked rather than
   absent.
6. **No fee market.** The miner accepts pending transactions in sequence order
   and the queue has no eviction policy, no minimum fee and no size limit.
7. **No peer defence.** There is no rate limiting, no peer banning, no scoring
   and no proof-of-work requirement on gossip. The 8 MiB body cap is the only
   protection, and it is not sufficient against a determined attacker.
8. **Unauthenticated transport.** Plain HTTP. Peer identity is whatever a peer
   claims. Transport encryption exists only when a hosting provider terminates
   TLS in front of the node.
9. **Not constant-time.** The curve arithmetic branches and allocates on
   secret-dependent values. On a machine where an attacker can measure timing or
   cache behaviour, private keys may leak. This code should not hold value on a
   shared host.
10. **Single-process locking.** The node serialises its own writes with a
    reentrant lock, and writes files atomically via `os.replace`. It does **not**
    coordinate with a separate process; mining from the command line while the
    node is serving can lose a block to a lost update.
11. **Residual time-warp.** §8.
12. **Non-standard MuSig tags.** The key aggregation of §14 uses the tags
    `Tempest/agg/lista` and `Tempest/agg/coef`, not those of the published
    MuSig2 specification. It is correct within Tempest and interoperable with
    nothing.
13. **Two-of-two only.** Joint accounts are 2-of-2. There is no k-of-n, and no
    way to spend with a participant missing.
14. **Bounded difficulty.** Clamping difficulty to [3, 7] bounds the work any
    block can carry, so the chain cannot become arbitrarily expensive to rewrite
    regardless of how much hash power joins.
15. **No subdivision.** A value is an integer number of TEMP. There is no
    decimal place, no base unit, no satoshi. Bitcoin does not have 21 million
    units; it has 2.1 × 10¹⁵ satoshis, and "1 BTC" is a display convention.
    Tempest has 1,890 indivisible units — twelve orders of magnitude less
    granularity — and this is measurable, not theoretical:

    - The minimum fee of 1 TEMP is **0.053% of the entire supply**. A
      proportionally equal fee in Bitcoin would be about 11,000 BTC.
    - The halving truncates at whole coins, so the issuance curve loses money
      at every step: 50, 25, 12, 6, 3, 1. The twelve should be 12.5.
    - **60 TEMP of 1,950 do not exist** (§10). Three per cent of the money was
      destroyed by rounding before anyone spent anything.

    The fix is the one Bitcoin made: declare 1 TEMP = 10⁸ base units, store
    every amount in base units and divide only for display. It costs three
    constants and a chain reset, and it costs nothing pedagogically — the
    halving would still arrive in a minute. It is listed here rather than
    applied because the chain is live and the defect teaches something while
    it stands.

16. **The token.** TEMP has no price, no market and no path to either. Section
    16 explains why this is not a problem awaiting a solution.

---

## 13. Verifying this document

Every claim above is checkable. These are the commands.

```bash
python3 cadeia.py validar            # the whole chain, from block zero
python3 cadeia.py adulterar 3        # attack 1: rewrite the past
python3 cadeia.py repetir            # attack 2: replay a signed transaction
python3 cadeia.py atrasar            # attack 3: lie about the clock
python3 cadeia.py prova 4 0          # a Merkle inclusion proof
python3 schnorr.py vetores           # the 19 official BIP-340 vectors
python3 schnorr.py ataque            # the rogue-key attack, with the defence
python3 partilha.py provar           # k−1 shares reveal nothing
python3 pollard.py lei               # the square-root law, measured
python3 pollard.py conta             # attack cost on this machine
```

The 88-byte header can be hashed without Python, which is the point of §5.1:

```bash
python3 -c "
import cadeia as C
open('h.bin','wb').write(C.cabecalho_bytes(C.carrega_cadeia()[-1]))"
sha256sum h.bin
```

And the chain can be audited from outside the node that serves it — downloading
the raw bytes, re-deriving everything locally, and only then reading a balance:

```bash
python3 -c "
import json, urllib.request, cadeia as C
c = json.load(urllib.request.urlopen('http://NODE/cadeia', timeout=30))
print(C.valida(c))
print(C.saldos(c).get('<address>', 0))"
```

This is what a block explorer is.

---

## 14. Joint accounts

Schnorr signatures are **linear**, and ECDSA signatures are not. The sum of two
signatures over the sum of two keys is a valid signature of the summed key.
Tempest uses this directly.

Two owners add their public keys. The result is an address whose private key
**does not exist** — neither of them knows it, and no one ever will. Spending
from it requires both signing together. What enters the block is a 32-byte key
and a 64-byte signature, indistinguishable from a single signer's. The chain
gained no new field, no new rule, and has no way to know the account belongs to
two people.

Adding the keys naively is a hole. If Bob waits for Alice's key and publishes
`Pb = x·G − Pa`, the sum becomes `x·G` and he signs alone for both. The defence
is MuSig's: each key enters multiplied by a coefficient derived from a hash of
the entire sorted key list, so no one can choose theirs after seeing the others.

```
L   = H_tag("Tempest/agg/lista", sorted(P₁ ‖ … ‖ Pₙ))
aᵢ  = H_tag("Tempest/agg/coef", L ‖ Pᵢ)  mod n
Q   = Σ aᵢ · Pᵢ
```

`schnorr.py ataque` runs the attack with and without the defence, side by side.

Two honest notes on scope. The command-line demonstration reads both private
keys in a single process, which is precisely what is not done in practice: each
owner holds their own on a separate machine, and the protocol has rounds whose
**order** is the entire point — nonces must be exchanged *before* any partial
signature, or whoever speaks last picks their nonce after seeing the others and
forges the group's signature, which is the rogue-key pattern again. And it is
2-of-2, not k-of-n.

---

## 15. The cost of breaking this

A private key is a number *k*; the public key is the point `Q = k·G`. Breaking
the key means finding *k* given *Q* — the discrete logarithm problem. Brute
force costs *n* attempts, where *n* is the group order. **Pollard's rho costs
the square root of n.**

That square root answers a question almost nobody asks: why 256 bits and not
128? Because the best known attack needs 2¹²⁸ steps against a 256-bit key.
secp256k1 has a 256-bit key and 128 bits of security. Half the number is not
waste; it is the price of rho.

`pollard.py` runs the attack for real, on the same equation `y² = x³ + 7` over
small fields where the end can be waited for. Seven curves from 16 to 41 bits,
each with prime order verified at runtime against the Hasse interval. The
`lei` command repeats the attack across four orders and divides the step count
by `√n`; the constant `√(π/2) = 1.2533` appears in the final column without ever
having been written into the code.

`pollard.py canguru` is Pollard's lambda on **real secp256k1** — same generator,
same 256 bits — with the key drawn from a 28-bit interval, as in a wallet seeded
from a clock. Measured on a phone: 268 million possible keys resolved in about
seven seconds and roughly 30,000 point additions, none of them a guess at the
key.

`pollard.py conta` measures point additions per second on the machine it runs on
and extrapolates. On that same phone, at about 4,900 additions per second:

| | |
|---|---|
| Steps rho requires | 4.27 × 10³⁸ |
| Time on that device | 2.75 × 10²⁷ years |
| Age of the universe | 1.38 × 10¹⁰ years |
| The entire Bitcoin network, if every hash were a point addition | ≈ 1.1 × the age of the universe |

The last row is the one worth keeping. The security of a secp256k1 signature is
not "hard". It is every unit of computation humanity has ever pointed at one
thing, running since the Big Bang, and not finished.

One subtlety that closes the loop with §9. Rho and kangaroo buy the square root
only where the search space has **additive structure** — a whole group, or a
contiguous interval. Twelve words have neither: PBKDF2 scatters the 2¹²⁸
candidates across the group with no additive relation among them, and without
structure there is no square-root shortcut. An attacker must try them one at a
time. Twelve words are therefore worth a full 128 bits of security — exactly the
level of the curve itself. More entropy in the phrase would buy nothing, because
rho already caps the other side at 2¹²⁸. BIP-39 did not choose 128 bits by
accident.

What breaks in practice is the opposite: keys drawn from an interval. That is
what the Bitcoin "puzzle" addresses are, and why they are swept as the bit
frontier advances.

---

## 16. On what this is for

Tempest has the complete mechanism and none of the other half.

The other half is people: thousands of independent machines simultaneously
refusing the same lie, and someone willing to trade something real for the
result. Bitcoin's source has been public since 2009 and copied thousands of
times. There are thousands of coins that are Bitcoin with the name changed, and
nearly all of them are worth zero. If writing the code were the hard part,
anyone would be rich.

Writing the code was two days on a phone. What is hard is the rest, and no
amount of engineering supplies it. Mining does not create value; miners follow
value, because electricity costs money. In a proof-of-work chain the security
*is* the cost of attacking it, and that cost is proportional to the price — zero
price, zero security; zero security, nothing worth storing; zero price. Bitcoin
escaped that loop in 2009 with a decade of people believing before there was a
reason to, not with better code.

So TEMP is worth nothing, and this specification says so in its abstract rather
than its appendix. The value of Tempest was never in the token. It is in the
fact that every claim in this document can be checked by running a command, and
that a reader who has run them can go and read somebody else's chain and tell
whether it is serious.

---

## References

- Satoshi Nakamoto, *Bitcoin: A Peer-to-Peer Electronic Cash System*, 2008
- Certicom Research, *SEC 2: Recommended Elliptic Curve Domain Parameters*
- BIP-340, *Schnorr Signatures for secp256k1*
- BIP-39, *Mnemonic code for generating deterministic keys*
- BIP-32, *Hierarchical Deterministic Wallets* (referenced, not implemented)
- Adi Shamir, *How to Share a Secret*, Communications of the ACM, 1979
- J. M. Pollard, *Monte Carlo Methods for Index Computation (mod p)*, 1978
- J. M. Pollard, *Kangaroos, Monopoly and Discrete Logarithms*, 2000
- Maxwell, Poelstra, Seurin, Wuille, *Simple Schnorr Multi-Signatures*, 2018

---

Source: <https://github.com/Eduardo010470/tempest> · MIT licence
