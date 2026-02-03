decimal

\ Reload safety:
\ Re-sending this file repeatedly grows the dictionary until the ESP32 hard-faults.
\ We install a small anchor word (`br-dev`) so each load can `forget` the previous bedrock build.
only forth definitions
s" cd-dev" find 0<> [if] forget cd-dev [then]  \ legacy reload anchor (pre-Bedrock rename)
s" br-dev" find 0<> [if] forget br-dev [then]
: br-dev ( -- ) ;  \ reload anchor (used by `forget` above)

\ ESP32forth hides many useful implementation words in the `internals` vocabulary.
\ We opt-in so we can build a quiet, protocol-first command loop.
only forth definitions also internals also interrupts

\ Bedrock Protocol (ESP32 / ESP32forth)
\ TODO(thesis): Replace dummy sampling with real sensor read + timestamp source.
\ TODO(thesis): Extend rollback beyond single last-known-good (and document flash-wear tradeoffs).
\ TODO(thesis): Replace `bye`-based reboot with a clean ESP32 restart primitive.

vocabulary br-user
' br-user >body constant br-user-wordlist

256 constant br-fifo-size
create br-fifo br-fifo-size 2* cells allot  \ value, timestamp pairs

variable br-head
variable br-count
variable br-tick

: br-clear ( -- ) 0 br-head ! 0 br-count ! ;

: br-min ( a b -- a|b ) 2dup < if drop else swap drop then ;
: br-submod ( idx n mod -- idx' ) >r swap r@ + swap - r> mod ;
: br-adv ( a n -- a' n' ) 1- swap 1+ swap ;
: br-drop1 ( a n -- a' n' ) 1- swap 1+ swap ;
: br-/string ( a n u -- a' n' ) >r swap r@ + swap r> - ;
: br-space? ( c -- f ) dup bl = over 9 = or over 10 = or swap 13 = or ;
: br-skip-spaces ( a n -- a' n' )
  begin dup while over c@ br-space? if br-adv else exit then repeat ;

: br-addr ( idx -- addr ) 2* cells br-fifo + ;

: br-write ( value ts idx -- )
  br-addr dup cell+ >r
  over r@ !            \ ts -> addr+cell
  swap drop !          \ value -> addr
  r> drop ;

: br-inc-count ( -- )
  br-count @ br-fifo-size < if br-count @ 1+ br-count ! then ;

: br-push ( value ts -- )
  br-head @ br-write
  br-head @ 1+ br-fifo-size mod br-head !
  br-inc-count ;

: br-read ( idx -- value ts ) br-addr dup @ swap cell+ @ ;

: br.!end ( -- ) ." ! end" cr ;
: br.!ok ( -- ) ." ! ok" cr ;
: br.!sample ( value ts -- ) ." ! " swap . . cr ;
: br.# ( a n -- ) ." # " type cr ;

variable br-error-emitted
: br-error-reset ( -- ) 0 br-error-emitted ! ;
: br-error-on ( -- ) -1 br-error-emitted ! ;
: br.#err ( a n -- ) br-error-on ." # err " type cr ;
: br.#code ( n -- ) br-error-on ." # code " . cr ;
: br-consume-line ( -- ) #tib @ >in ! ;
: br-rest-of-line ( -- a n )
  tib >in @ +  #tib @ >in @ - ;

: br-next-ts ( -- u ) br-tick @ dup 1+ br-tick ! ;
: br-next-sample ( -- value ts ) br-next-ts dup ;

: 0<> ( n -- f ) 0= 0= ;
: 0> ( n -- f ) 0 > ;
: br-exit postpone exit ; immediate

: 2swap ( a b c d -- c d a b ) rot >r rot r> ;
: 2over ( a b c d -- a b c d a b ) >r >r 2dup r> r> 2swap ;

: br-parse-int-or ( default -- n )
  bl parse dup 0= if 2drop exit then
  rot drop evaluate ;

\ ------------------------------------------------------------
\ User vocabulary helpers

  \ NOTE: ESP32forth does not provide `search-wordlist` / `get-order`.
  \ For `define` we use `find` with a fixed search order (see `define`).

variable br-define-current
: br-define-current-save ( -- ) current @ br-define-current ! ;
: br-define-current-restore ( -- ) br-define-current @ current ! ;

variable br-define-la
variable br-define-ln
variable br-define-na
variable br-define-nn

variable br-token-a
variable br-token-n
variable br-token-len

: br-token ( a n -- aTok nTok aRest nRest f )
  br-skip-spaces
  dup 0= if 2drop 0 0 0 0 0 exit then
  2dup br-token-n ! br-token-a ! 2drop
  0 br-token-len !
  br-token-a @ br-token-n @                           \ aCur nCur
  begin
    dup 0> if
      over c@ br-space? 0=
    else
      0
    then
  while
    br-adv
    1 br-token-len +!
  repeat
  br-token-a @ br-token-len @ 2swap -1 ;

: br-colon-token? ( a n -- f ) 1 = swap c@ [char] : = and ;
: br-4drop ( a b c d -- ) 2drop 2drop ;
: br-5drop ( a b c d e -- ) drop br-4drop ;

\ Parse `: name ... ;` from a line and return the `name` token.
: br-define-name ( a n -- a n f )
  br-token dup 0= if br-5drop 0 0 0 exit then drop             \ aTok nTok aR nR
  2over br-colon-token? 0= if 2drop 2drop 0 0 0 exit then
  2swap 2drop                                                   \ aR nR
  br-token dup 0= if br-5drop 0 0 0 exit then drop              \ aName nName aR2 nR2
  2drop                                                         \ aName nName
  -1 ;

\ ------------------------------------------------------------
\ Files (SPIFFS) helpers

4 constant br-safe-gpio  \ DOIT ESP32 DEVKIT V1: user wired button between GPIO4 and GND.

64 constant br-path-max
create br-myforth-path br-path-max allot
variable br-myforth-n

: br-myforth-build ( -- )
  remember-filename dup br-myforth-n ! br-myforth-path swap cmove
  br-myforth-path br-myforth-n @ + 0 swap c! ;

: br-myforth$ ( -- a n ) br-myforth-path br-myforth-n @ ;

64 constant br-lkg-max
create br-lkg-path br-lkg-max allot
variable br-lkg-n

: br-lkg-build ( -- )
  br-myforth$ dup br-lkg-n ! br-lkg-path swap cmove
  s" .lkg" br-adv dup >r
  br-lkg-path br-lkg-n @ + swap cmove
  br-lkg-n @ r@ + dup br-lkg-n !
  br-lkg-path + 0 swap c!
  r> drop ;

: br-lkg$ ( -- a n ) br-lkg-path br-lkg-n @ ;

: br-file-exists? ( a n -- f )
  r/o open-file dup 0<> if
    drop drop 0 exit
  then
  drop close-file drop -1 ;

\ Copy a file on SPIFFS (best-effort, used for safe-save LKG).
256 constant br-copy-buf-size
create br-copy-buf br-copy-buf-size allot

: (br-copy-file) { sa sn da dn -- }
  sa sn r/o open-file throw { sfid }
  da dn delete-file drop
  da dn w/o create-file throw { dfid }
  begin
    br-copy-buf br-copy-buf-size sfid read-file throw { nread }
    nread 0= if leave then
    br-copy-buf nread dfid write-file throw
  again
  sfid close-file throw
  dfid close-file throw ;

: br-copy-file ( sa sn da dn -- ok? ) ['] (br-copy-file) catch 0= ;

\ ------------------------------------------------------------
: br-dump ( n -- )
  dup 0= if drop br.!end exit then
  dup >r
  br-head @ r@ br-fifo-size br-submod
  r@ 0 ?do
    dup i + br-fifo-size mod br-read br.!sample
  loop
  drop
  r> drop
  br.!end ;

\ ------------------------------------------------------------
\ History (persistent, SPIFFS)

: br-history-path$ ( -- a n ) s" /spiffs/bedrock.history" ;
create br-nl 1 allot
create br-sp 1 allot

: br-now ( -- u ) br-next-ts ;

: br-nl-init ( -- ) 10 br-nl c! bl br-sp c! ;

: br-open-append ( a n -- fid )
  2dup r/w open-file
  dup 0<> if
    drop drop
    r/w create-file throw
  else
    drop -rot 2drop
  then
  >r
  r@ file-size throw r@ reposition-file throw
  r> ;

: br-write-nl ( fid -- ) br-nl 1 rot write-file throw ;
: br-write-space ( fid -- ) br-sp 1 rot write-file throw ;
: br-write-u ( u fid -- )
  >r <# #s #> r> write-file throw ;

160 constant br-history-line-max
create br-history-line br-history-line-max allot
variable br-history-ln
create br-history-ch 1 allot

: br-eol? ( c -- f ) dup 10 = swap 13 = or ;
: br-history-line-clear ( -- ) 0 br-history-ln ! ;
: br-history-line-flush ( -- )
  br-history-ln @ dup 0> if
    ." ! " br-history-line swap type cr
  else
    drop
  then
  br-history-line-clear ;

: br-history-line-add ( c -- )
  br-history-ln @ br-history-line-max >= if br-history-line-flush then
  br-history-line br-history-ln @ + c!
  1 br-history-ln +! ;

: (br-history-event) { a n -- }
  br-history-path$ br-open-append { fid }
  br-now fid br-write-u
  fid br-write-space
  a n fid write-file throw
  fid br-write-nl
  fid close-file throw ;

: (br-history-event+) { ea en pa pn -- }
  br-history-path$ br-open-append { fid }
  br-now fid br-write-u
  fid br-write-space
  ea en fid write-file throw
  pn 0<> if
    fid br-write-space
    pa pn fid write-file throw
  then
  fid br-write-nl
  fid close-file throw ;

: br-history-event ( a n -- ) ['] (br-history-event) catch drop ;
: br-history-event+ ( ea en pa pn -- ) ['] (br-history-event+) catch drop ;

: (br-history-event-kv) { ea en ka kn va vn -- }
  br-history-path$ br-open-append { fid }
  br-now fid br-write-u
  fid br-write-space
  ea en fid write-file throw
  fid br-write-space
  ka kn fid write-file throw
  fid br-write-space
  va vn fid write-file throw
  fid br-write-nl
  fid close-file throw ;

: br-history-event-kv ( ea en ka kn va vn -- ) ['] (br-history-event-kv) catch drop ;

: history ( -- )
  br-history-path$ r/o open-file dup 0<> if drop drop br.!end exit then
  drop { fid }
  br-history-line-clear
  begin
    br-history-ch 1 fid read-file throw dup
  while
    drop
    br-history-ch c@ dup br-eol? if
      drop br-history-line-flush
    else
      br-history-line-add
    then
  repeat
  drop
  br-history-line-flush
  fid close-file throw
  br.!end ;

\ ------------------------------------------------------------
\ Metadata (persistent, SPIFFS)

: br-meta-path$ ( -- a n ) s" /spiffs/bedrock.meta" ;
16 constant br-meta-max
16 constant br-meta-key-max
32 constant br-meta-val-max
br-meta-key-max 1+ constant br-meta-key-entry
br-meta-val-max 1+ constant br-meta-val-entry

create br-meta-keys br-meta-max br-meta-key-entry * allot
create br-meta-vals br-meta-max br-meta-val-entry * allot
variable br-meta-count
variable br-meta-tka
variable br-meta-tkn
variable br-meta-tva
variable br-meta-tvn

: br-meta-clear ( -- ) 0 br-meta-count ! ;
: br-meta-kaddr ( idx -- a ) br-meta-key-entry * br-meta-keys + ;
: br-meta-vaddr ( idx -- a ) br-meta-val-entry * br-meta-vals + ;
: br-meta-kread ( idx -- a n )
  br-meta-kaddr dup c@ swap 1+ swap ;
: br-meta-vread ( idx -- a n )
  br-meta-vaddr dup c@ swap 1+ swap ;
: br-meta-kwrite ( a n idx -- )
  br-meta-kaddr >r
  br-meta-key-max br-min dup r@ c!
  r@ 1+ swap cmove
  r> drop ;
: br-meta-vwrite ( a n idx -- )
  br-meta-vaddr >r
  br-meta-val-max br-min dup r@ c!
  r@ 1+ swap cmove
  r> drop ;

: br-meta-find { a n -- idx|-1 }
  br-meta-count @ 0 ?do
    i br-meta-kread a n str= if i unloop exit then
  loop
  -1 ;

: br-meta-set { ka kn va vn -- ok? }
  ka kn br-meta-find dup -1 <> if
    va vn rot br-meta-vwrite
    -1 exit
  then
  drop
  br-meta-count @ br-meta-max >= if 0 exit then
  ka kn br-meta-count @ br-meta-kwrite
  va vn br-meta-count @ br-meta-vwrite
  br-meta-count @ 1+ br-meta-count !
  -1 ;

: (br-meta-save) ( -- )
  br-meta-path$ delete-file drop
  br-meta-path$ w/o create-file throw { fid }
  br-meta-count @ 0 ?do
    i br-meta-kread fid write-file throw
    fid br-write-space
    i br-meta-vread fid write-file throw
    fid br-write-nl
  loop
  fid close-file throw ;

: br-meta-save ( -- ok? ) ['] (br-meta-save) catch 0= ;

: br-meta-load-buf ( a n -- )
  begin
    br-token dup 0= if br-5drop exit then drop            \ ka kn aR nR
    br-token dup 0= if br-5drop 2drop exit then drop      \ ka kn va vn aR2 nR2
    >r >r br-meta-set drop r> r>
  again ;

: (br-meta-load) ( -- )
  br-meta-clear
  br-meta-path$ r/o open-file dup 0<> if drop drop exit then
  drop { fid }
  fid file-size throw { size }
  size 0= if fid close-file throw exit then
  size allocate throw { buf }
  buf size fid read-file throw drop
  fid close-file throw
  buf size br-meta-load-buf
  buf free throw ;

: br-meta-load ( -- ) ['] (br-meta-load) catch drop ;

\ Metadata lookup

: br-meta-get$ ( ka kn -- va vn f )
  br-meta-find dup -1 = if drop 0 0 0 exit then
  br-meta-vread -1 ;

: br-id$ ( -- a n )
  s" id" br-meta-get$ dup if
    drop
  else
    drop 2drop
    s" smart"
  then ;

: br-role$ ( -- a n )
  s" role" br-meta-get$ dup if
    drop
  else
    drop 2drop
    s" smart"
  then ;

: br-ver$ ( -- a n )
  s" ver" br-meta-get$ dup if
    drop
  else
    drop 2drop
    s" bedrock-0.1"
  then ;

: br-children$ ( -- a n )
  s" children" br-meta-get$ dup if
    drop
  else
    drop 2drop
    s" 0"
  then ;

: br-board$ ( -- a n f )
  s" board" br-meta-get$ ;

: br.!meta-if { ka kn la ln -- }
  ka kn br-meta-get$ dup if
    drop
    ." ! " la ln type space type cr
  else
    drop 2drop
  then ;

: meta ( -- )
  br-rest-of-line br-skip-spaces
  br-consume-line
  dup 0= if
    2drop
    br-meta-count @ 0 ?do
      ." ! " i br-meta-kread type space i br-meta-vread type cr
    loop
    br.!end
    exit
  then
  br-token dup 0= if br-5drop s" meta_syntax" br.#err br.!end exit then drop  \ ka kn aR nR
  2swap br-skip-spaces 2swap                                                     \ ka kn aR' nR'
  dup 0= if                                                                      \ meta <key>
    2drop
    2dup br-meta-find dup -1 = if
      drop 2drop
      s" meta_missing" br.#err br.!end exit
    then
    >r
    ." ! " 2dup type space
    r> br-meta-vread type cr
    2drop
    br.!end
    exit
  then
  br-token dup 0= if br-5drop 2drop s" meta_syntax" br.#err br.!end exit then drop  \ ka kn va vn aR2 nR2
  br-skip-spaces dup 0<> if
    2drop 2drop 2drop
    s" meta_syntax" br.#err br.!end exit
  then
  2drop                                                                            \ ka kn va vn
  2dup br-meta-tvn ! br-meta-tva !                                                 \ stash value
  2swap 2dup br-meta-tkn ! br-meta-tka ! 2swap                                     \ stash key
  br-4drop
  br-meta-tka @ br-meta-tkn @ br-meta-tva @ br-meta-tvn @ br-meta-set 0= if
    s" meta_full" br.#err br.!end exit
  then
  br-meta-save 0= if
    s" meta_io" br.#err br.!end exit
  then
  s" meta" br-meta-tka @ br-meta-tkn @ br-meta-tva @ br-meta-tvn @ br-history-event-kv
  br.!ok
  br.!end ;

\ ------------------------------------------------------------
\ Pin Registry (Milestone E: Hardware Affordances)
\ Tracks Bedrock-level ownership and state for GPIO 0-39.
\ Physical layout lives in terminal tooling (board manifests).

40 constant br-pin-max

\ Mode enum: 0=unknown, 1=in, 2=out, 3=adc, 4=i2c, 5=uart, 6=pwm, 7=reserved
create br-pin-mode br-pin-max allot
\ Pull enum: 0=none, 1=up, 2=down
create br-pin-pull br-pin-max allot
\ Flags bitmask: 1=safe, 2=strapping, 4=input-only, 8=flash
create br-pin-flags br-pin-max allot
\ Drive value: 0/1 when last written (meaningful for mode=out)
create br-pin-drive br-pin-max allot
\ Owner: 8 bytes per pin (length byte + 7 chars)
8 constant br-pin-owner-max
create br-pin-owner br-pin-max br-pin-owner-max * allot

: br-pin-mode@ ( gpio -- mode ) br-pin-mode + c@ ;
: br-pin-mode! ( mode gpio -- ) br-pin-mode + c! ;
: br-pin-pull@ ( gpio -- pull ) br-pin-pull + c@ ;
: br-pin-pull! ( pull gpio -- ) br-pin-pull + c! ;
: br-pin-flags@ ( gpio -- flags ) br-pin-flags + c@ ;
: br-pin-flags! ( flags gpio -- ) br-pin-flags + c! ;
: br-pin-drive@ ( gpio -- v ) br-pin-drive + c@ ;
: br-pin-drive! ( v gpio -- ) br-pin-drive + c! ;
: br-pin-owner-addr ( gpio -- a ) br-pin-owner-max * br-pin-owner + ;
: br-pin-owner@ ( gpio -- a n ) br-pin-owner-addr dup c@ swap 1+ swap ;
: br-pin-owner! ( a n gpio -- )
  br-pin-owner-addr >r
  br-pin-owner-max 1- br-min dup r@ c!
  r@ 1+ swap cmove
  r> drop ;
: br-pin-owner-clear ( gpio -- ) 0 swap br-pin-owner-addr c! ;

\ Initialize registry to defaults
: br-pin-registry-init ( -- )
  br-pin-max 0 do
    0 i br-pin-mode!
    0 i br-pin-pull!
    0 i br-pin-flags!
    0 i br-pin-drive!
    i br-pin-owner-clear
  loop
  \ Mark known ESP32 constraints
  \ Flash pins (6-11): flag=8
  6 11 do 8 i br-pin-flags! loop
  \ Input-only pins (34-39): flag=4
  34 40 do 4 i br-pin-flags! loop
  \ Strapping pins (0,2,5,12,15): flag=2
  2 0 br-pin-flags!
  2 2 br-pin-flags!
  2 5 br-pin-flags!
  2 12 br-pin-flags!
  2 15 br-pin-flags!
  \ SAFE pin (GPIO4): flag=1 (safe)
  1 br-safe-gpio br-pin-flags! ;

\ Pin token parsing: accept "4", "D4", "GPIO4" (case-insensitive)
variable br-parse-gpio-num
variable br-parse-gpio-ok

: br-digit? ( c -- f ) dup [char] 0 >= swap [char] 9 <= and ;
: br-to-upper ( c -- c' ) dup [char] a >= over [char] z <= and if 32 - then ;

: br-parse-digits ( a n -- gpio f )
  0 br-parse-gpio-num !
  dup 0= if 2drop 0 0 exit then
  begin dup while
    over c@ br-digit? 0= if 2drop 0 0 exit then
    over c@ [char] 0 - br-parse-gpio-num @ 10 * + br-parse-gpio-num !
    br-adv
  repeat
  2drop
  br-parse-gpio-num @ dup br-pin-max < if -1 else drop 0 0 then ;

: br-parse-gpio ( a n -- gpio f )
  dup 0= if 2drop 0 0 exit then
  over c@ br-to-upper
  dup [char] D = if
    drop br-adv br-parse-digits exit
  then
  dup [char] G = if
    drop
    dup 4 >= if
      over 1+ c@ br-to-upper [char] P = if
      over 2 + c@ br-to-upper [char] I = if
      over 3 + c@ br-to-upper [char] O = if
        4 br-/string br-parse-digits exit
      then then then
    then
    2drop 0 0 exit
  then
  br-digit? if br-parse-digits exit then
  2drop 0 0 ;

\ Mode token to enum
: br-mode-token ( a n -- enum f )
  2dup s" unknown" str= if 2drop 0 -1 exit then
  2dup s" in" str= if 2drop 1 -1 exit then
  2dup s" out" str= if 2drop 2 -1 exit then
  2dup s" adc" str= if 2drop 3 -1 exit then
  2dup s" i2c" str= if 2drop 4 -1 exit then
  2dup s" uart" str= if 2drop 5 -1 exit then
  2dup s" pwm" str= if 2drop 6 -1 exit then
  2dup s" reserved" str= if 2drop 7 -1 exit then
  2drop 0 0 ;

\ Enum to mode token
: br-mode$ ( enum -- a n )
  dup 0 = if drop s" unknown" exit then
  dup 1 = if drop s" in" exit then
  dup 2 = if drop s" out" exit then
  dup 3 = if drop s" adc" exit then
  dup 4 = if drop s" i2c" exit then
  dup 5 = if drop s" uart" exit then
  dup 6 = if drop s" pwm" exit then
  dup 7 = if drop s" reserved" exit then
  drop s" unknown" ;

\ Pull token to enum
: br-pull-token ( a n -- enum f )
  2dup s" none" str= if 2drop 0 -1 exit then
  2dup s" up" str= if 2drop 1 -1 exit then
  2dup s" down" str= if 2drop 2 -1 exit then
  2drop 0 0 ;

\ Enum to pull token
: br-pull$ ( enum -- a n )
  dup 0 = if drop s" none" exit then
  dup 1 = if drop s" up" exit then
  dup 2 = if drop s" down" exit then
  drop s" none" ;

\ Flags to comma-separated token
create br-flags-buf 32 allot
variable br-flags-len

: br-flags-add ( a n -- )
  br-flags-len @ 0> if
    [char] , br-flags-buf br-flags-len @ + c!
    1 br-flags-len +!
  then
  dup br-flags-len @ + 32 > if 2drop exit then
  br-flags-buf br-flags-len @ + swap dup br-flags-len +! cmove ;

: br-flags$ ( flags -- a n )
  0 br-flags-len !
  dup 1 and if s" safe" br-flags-add then
  dup 2 and if s" strapping" br-flags-add then
  dup 4 and if s" input-only" br-flags-add then
  dup 8 and if s" flash" br-flags-add then
  drop
  br-flags-len @ 0= if s" -" else br-flags-buf br-flags-len @ then ;

\ Check if pin is safe to read (not flash pin)
: br-pin-readable? ( gpio -- f ) br-pin-flags@ 8 and 0= ;

\ Emit single pin status line
: br.!pin ( gpio -- )
  ." ! pin gpio=" dup . space
  ." mode=" dup br-pin-mode@ br-mode$ type space
  ." drive="
  dup br-pin-mode@ 2 = if
    dup br-pin-drive@ .
  else
    ." - "
  then
  space
  ." level="
  dup br-pin-readable? if
    dup gpio_get_level .
  else
    ." - "
  then
  ." pull=" dup br-pin-pull@ br-pull$ type space
  ." owner="
  dup br-pin-owner@ dup 0= if 2drop ." -" else type then
  space
  ." flags=" br-pin-flags@ br-flags$ type
  cr ;

\ Protocol command: pins (bulk dump)
: pins ( -- )
  br-board$ if ." ! board " type cr else 2drop then
  br-pin-max 0 do i br.!pin loop
  br.!end ;

\ Protocol command: pin-status <pin>
: pin-status ( -- )
  bl parse br-skip-spaces
  dup 0= if 2drop s" pin_syntax" br.#err br.!end exit then
  br-parse-gpio 0= if s" pin_range" br.#err br.!end exit then
  br.!pin
  br.!end ;

\ Protocol command: pin-claim <pin> <owner>
: pin-claim ( -- )
  bl parse br-skip-spaces
  dup 0= if 2drop s" pin_syntax" br.#err br.!end exit then
  br-parse-gpio 0= if s" pin_range" br.#err br.!end exit then
  { gpio }
  bl parse br-skip-spaces
  dup 0= if 2drop s" pin_syntax" br.#err br.!end exit then
  { oa on }
  gpio br-pin-owner@ dup 0> if
    oa on str= 0= if
      s" pin_owned" br.#err br.!end exit
    then
  else
    2drop
  then
  oa on gpio br-pin-owner!
  br.!ok br.!end ;

\ Protocol command: pin-release <pin>
: pin-release ( -- )
  bl parse br-skip-spaces
  dup 0= if 2drop s" pin_syntax" br.#err br.!end exit then
  br-parse-gpio 0= if s" pin_range" br.#err br.!end exit then
  br-pin-owner-clear
  br.!ok br.!end ;

\ Protocol command: pin-mode <pin> in|out [pull=up|down|none]
: pin-mode ( -- )
  bl parse br-skip-spaces
  dup 0= if 2drop s" pin_syntax" br.#err br.!end exit then
  br-parse-gpio 0= if s" pin_range" br.#err br.!end exit then
  { gpio }
  \ Check if flash pin
  gpio br-pin-flags@ 8 and if s" pin_flash" br.#err br.!end exit then
  \ Parse mode
  bl parse br-skip-spaces
  dup 0= if 2drop s" pin_syntax" br.#err br.!end exit then
  2dup s" in" str= if
    2drop
    gpio INPUT gpio_set_direction drop
    1 gpio br-pin-mode!
  else
    2dup s" out" str= if
      2drop
      \ Check if input-only pin
      gpio br-pin-flags@ 4 and if s" pin_input_only" br.#err br.!end exit then
      gpio OUTPUT gpio_set_direction drop
      2 gpio br-pin-mode!
    else
      2drop s" pin_mode_invalid" br.#err br.!end exit
    then
  then
  \ Parse optional pull=xxx
  bl parse br-skip-spaces
  dup 0> if
    \ Expect "pull=xxx"
    2dup 5 min s" pull=" str= if
      5 br-/string
      2dup s" up" str= if
        2drop gpio gpio_pullup_en drop 1 gpio br-pin-pull!
      else
        2dup s" down" str= if
          2drop gpio gpio_pulldown_en drop 2 gpio br-pin-pull!
        else
          2dup s" none" str= if
            2drop
            gpio gpio_pullup_dis drop
            gpio gpio_pulldown_dis drop
            0 gpio br-pin-pull!
          else
            2drop s" pin_pull_invalid" br.#err br.!end exit
          then
        then
      then
    else
      2drop s" pin_syntax" br.#err br.!end exit
    then
  else
    2drop
  then
  br.!ok br.!end ;

\ Protocol command: pin-read <pin>
: pin-read ( -- )
  bl parse br-skip-spaces
  dup 0= if 2drop s" pin_syntax" br.#err br.!end exit then
  br-parse-gpio 0= if s" pin_range" br.#err br.!end exit then
  dup br-pin-readable? 0= if drop s" pin_flash" br.#err br.!end exit then
  ." ! value " gpio_get_level . cr
  br.!end ;

\ Protocol command: pin-write <pin> 0|1
: pin-write ( -- )
  bl parse br-skip-spaces
  dup 0= if 2drop s" pin_syntax" br.#err br.!end exit then
  br-parse-gpio 0= if s" pin_range" br.#err br.!end exit then
  { gpio }
  \ Check constraints
  gpio br-pin-flags@ 8 and if s" pin_flash" br.#err br.!end exit then
  gpio br-pin-flags@ 4 and if s" pin_input_only" br.#err br.!end exit then
  \ Writes are output semantics: ensure OUTPUT mode unless already out.
  gpio br-pin-mode@ 2 <> if
    gpio OUTPUT gpio_set_direction drop
    2 gpio br-pin-mode!
  then
  \ Parse value
  bl parse br-skip-spaces
  dup 0= if 2drop s" pin_syntax" br.#err br.!end exit then
  2dup s" 0" str= if
    2drop 0 gpio br-pin-drive! gpio 0 gpio_set_level drop
  else
    2dup s" 1" str= if
      2drop 1 gpio br-pin-drive! gpio 1 gpio_set_level drop
    else
      2drop s" pin_value_invalid" br.#err br.!end exit
    then
  then
  br.!ok br.!end ;

\ Protocol commands (match PROTOCOL_REFERENCE.md)

: ? ( -- )
  ." ! id " br-id$ type cr
  ." ! role " br-role$ type cr
  ." ! mcu esp32" cr
  ." ! ver " br-ver$ type cr
  br-board$ if ." ! board " type cr else 2drop then
  ." ! fifo " br-fifo-size . cr
  s" units" 2dup br.!meta-if
  s" pins" 2dup br.!meta-if
  ." ! children " br-children$ type cr
  br.!end ;

: s ( -- )
  br-next-sample 2dup br-push br.!sample
  br.!end ;

: n ( -- )
  ." ! " br-count @ . cr
  br.!end ;

: d ( -- )
  br-count @ br-parse-int-or
  br-count @ br-min
  br-dump ;

: c ( -- )
  br-clear
  br.!ok
  br.!end ;

: explain ( -- )
  ." ! id " br-id$ type cr
  ." ! role " br-role$ type cr
  ." ! mcu esp32" cr
  ." ! ver " br-ver$ type cr
  br-board$ if ." ! board " type cr else 2drop then
  s" units" 2dup br.!meta-if
  s" pins" 2dup br.!meta-if
  ." ! children " br-children$ type cr
  ." ! fifo " br-fifo-size . cr
  ." ! core ? s n d c" cr
  ." ! extended explain source history define meta save validate safe-save restart recover rollback repl pins pin-status pin-claim pin-release pin-mode pin-read pin-write" cr
  br.!end ;

: br-validate? ( -- f )
  depth dup 0= swap -1 = or
  fdepth 0= and ;

: validate ( -- )
  br-validate? if
    br.!ok
  else
    ." ! fail stack" cr
  then
  br.!end ;

: define ( -- )
  br-rest-of-line br-skip-spaces
  2dup br-define-ln ! br-define-la ! 2drop
  br-define-la @ br-define-ln @ br-define-name 0= if
    s" define_syntax" br.#err br.!end br-consume-line 2drop br-exit
  then
  2dup br-define-nn ! br-define-na !
  2drop

  \ Reject redefining any existing word (new words only).
  br-define-na @ br-define-nn @ find 0<> if
    s" define_exists" br.#err br.!end br-consume-line br-exit
  then

  s" define" br-define-na @ br-define-nn @ br-history-event+
  br-consume-line
  br-define-current-save
  br-user-wordlist current !
  br-define-la @ br-define-ln @ evaluate
  br-define-current-restore
  br.!ok
  br.!end ;

\ ------------------------------------------------------------
\ Protocol-mode loop + error handling

: br-route ( a n -- )
  \ TODO(thesis): Implement routing to child nodes over UART/RS-485.
  s" route_unimplemented" br.#err
  ." # target " type cr
  br.!end ;

: br-notfound ( a n f -- )
  0= if 2drop exit then
  2dup over c@ [char] @ = if
    br-drop1 br-route
    br-consume-line
    2drop
    exit
  then
  s" notfound" br.#err
  2dup br.#
  br.!end
  br-consume-line
  2drop ;

: br-handle-exception ( n -- )
  br-error-emitted @ if drop br-error-reset exit then
  s" exception" br.#err
  br.#code
  br.!end
  br-error-reset ;

variable br-exit
variable br-old-echo
variable br-old-arrow
variable br-old-notfound

: repl ( -- )
  -1 br-old-echo !
  -1 br-old-arrow !
  -1 br-exit !
  -1 echo !
  -1 arrow !
  br.!ok
  br.!end ;

: br-call$ ( a n -- )
  2dup find dup 0= if
    drop
    s" notfound" br.#err
    2dup br.#
    br.!end
    2drop
    exit
  then
  >r
  2drop
  r> execute ;

: br-dispatch ( a n -- )
  dup 0= if 2drop exit then
  \ Routing prefix: @name cmd (Milestone D; currently unimplemented).
  2dup over c@ [char] @ = if
    br-drop1 br-route 2drop exit
  then
  2dup s" ?" str= if 2drop s" ?" br-call$ exit then
  2dup s" s" str= if 2drop s" s" br-call$ exit then
  2dup s" n" str= if 2drop s" n" br-call$ exit then
  2dup s" d" str= if 2drop s" d" br-call$ exit then
  2dup s" c" str= if 2drop s" c" br-call$ exit then
  2dup s" explain" str= if 2drop s" explain" br-call$ exit then
  2dup s" history" str= if 2drop s" history" br-call$ exit then
  2dup s" source" str= if 2drop s" source" br-call$ exit then
  2dup s" define" str= if 2drop s" define" br-call$ exit then
  2dup s" meta" str= if 2drop s" meta" br-call$ exit then
  2dup s" save" str= if 2drop s" save" br-call$ exit then
  2dup s" validate" str= if 2drop s" validate" br-call$ exit then
  2dup s" safe-save" str= if 2drop s" safe-save" br-call$ exit then
  2dup s" restart" str= if 2drop s" restart" br-call$ exit then
  2dup s" recover" str= if 2drop s" recover" br-call$ exit then
  2dup s" rollback" str= if 2drop s" rollback" br-call$ exit then
  2dup s" repl" str= if 2drop s" repl" br-call$ exit then
  2dup s" pins" str= if 2drop s" pins" br-call$ exit then
  2dup s" pin-status" str= if 2drop s" pin-status" br-call$ exit then
  2dup s" pin-claim" str= if 2drop s" pin-claim" br-call$ exit then
  2dup s" pin-release" str= if 2drop s" pin-release" br-call$ exit then
  2dup s" pin-mode" str= if 2drop s" pin-mode" br-call$ exit then
  2dup s" pin-read" str= if 2drop s" pin-read" br-call$ exit then
  2dup s" pin-write" str= if 2drop s" pin-write" br-call$ exit then
  s" notfound" br.#err
  2dup br.#
  br.!end
  2drop ;

: br-handle-line ( -- )
  \ Enforce protocol semantics: one request per line, no ambient stack state.
  0 state !
  sp0 sp!
  fp0 fp!
  br-error-reset

  \ Parse first token from the current TIB line.
  br-rest-of-line br-token dup 0= if br-5drop exit then drop   \ aTok nTok aRest nRest
  { aTok nTok aRest nRest }
  \ Advance >in so command words can parse arguments via `bl parse`.
  aRest tib - >in !
  aTok nTok br-dispatch
  br-consume-line ;

: br-node ( -- )
  echo @ br-old-echo !
  arrow @ br-old-arrow !
  'notfound @ br-old-notfound !

  0 br-exit !
  0 echo !
  0 arrow !
  ['] br-notfound 'notfound !
  begin
    br-exit @ 0<> if
      -1
    else
      refill 0= if
        10 ms
      else
        ['] br-handle-line catch ?dup if
          0 state ! sp0 sp! fp0 fp! rp0 rp!
          br-handle-exception
        then
      then
      0
    then
  until
  br-old-notfound @ 'notfound !
  br-old-echo @ echo !
  br-old-arrow @ arrow ! ;

: br-safe-setup ( -- )
  br-safe-gpio INPUT gpio_set_direction drop
  br-safe-gpio gpio_pullup_en drop ;

: br-safe-pressed? ( -- f ) br-safe-gpio gpio_get_level 0= ;

: br-boot ( -- )
  \ Reload persisted metadata from SPIFFS so `meta` survives resets without
  \ requiring a full image save.
  br-meta-path$ br-file-exists? if br-meta-load then
  br-safe-setup
  br-safe-pressed? if
    -1 echo !
    -1 arrow !
    ." SAFE: pressed; staying in REPL" cr
  else
    br-node
  then
  \ If `br-node` exits (e.g., via the `repl` protocol command), fall back to the
  \ standard ESP32forth REPL loop.
  quit ;

: br-ensure-autostart ( -- ) ['] br-boot 'cold ! ;

: save ( -- )
  \ Persist the current image to /spiffs/myforth and keep protocol auto-start enabled.
  br-ensure-autostart
  \ Also persist metadata to SPIFFS so it survives reloads that `forget` this image.
  br-meta-save drop
  remember
  s" save" br-history-event
  br.!ok
  br.!end ;

: safe-save ( -- )
  br-validate? if
    br-ensure-autostart
    \ Also persist metadata to SPIFFS so it survives reloads that `forget` this image.
    br-meta-save drop
    \ Backup last saved image before overwriting the primary remember file.
    br-myforth$ br-file-exists? if
      br-myforth$ br-lkg$ br-copy-file 0= if
        \ Best-effort: if the filesystem is too full to keep both images,
        \ proceed without a rollback image.
        br-lkg$ delete-file drop
      then
    then
    br-myforth$ save-name
    remember
    s" safe-save" br-history-event
    br.!ok
  else
    ." ! fail validate" cr
  then
  br.!end ;

: restart ( -- )
  ." ! rebooting" cr
  br.!end
  s" restart" br-history-event
  100 ms
  bye ;

: recover ( -- )
  \ Factory reset: delete saved images and reboot.
  s" recover" br-history-event
  br-myforth$ delete-file drop
  br-lkg$ delete-file drop
  br.!ok
  br.!end
  100 ms
  bye ;

: rollback ( -- )
  \ Minimal rollback: restore last-known-good image (myforth.lkg).
  1 br-parse-int-or dup 1 <> if
    drop s" unsupported" br.#err br.!end exit
  then
  drop
  br-lkg$ br-file-exists? 0= if
    s" rollback_missing" br.#err br.!end exit
  then
  s" rollback" br-history-event
  br.!ok
  br.!end
  br-lkg$ restore-name ;

\ Source: decompile key words, prefixing each output line with "! ".
variable br-old-type
variable br-line-start
create br-ch 1 allot

: br-type-xt@ ( -- xt ) ['] type >body @ ;
: br-type-xt! ( xt -- ) ['] type >body ! ;
: br-raw-type ( a n -- ) br-old-type @ execute ;
: br-raw-emit ( c -- ) br-ch c! br-ch 1 br-raw-type ;
: br-prefix ( -- ) s" ! " br-raw-type ;
: br-type-prefixed ( a n -- )
  begin dup while
    over c@ dup 13 = over 10 = or if
      br-raw-emit -1 br-line-start !
    else
      br-line-start @ if br-prefix 0 br-line-start ! then
      br-raw-emit
    then
    br-adv
  repeat 2drop ;

: source ( -- )
  br-type-xt@ br-old-type !
  ['] br-type-prefixed br-type-xt!
  -1 br-line-start !

  ['] ? see-xt
  ['] s see-xt
  ['] n see-xt
  ['] d see-xt
  ['] c see-xt
  ['] explain see-xt
  ['] history see-xt
  ['] define see-xt
  ['] meta see-xt
  ['] pins see-xt
  ['] pin-status see-xt
  ['] pin-claim see-xt
  ['] pin-release see-xt
  ['] pin-mode see-xt
  ['] pin-read see-xt
  ['] pin-write see-xt
  ['] save see-xt
  ['] validate see-xt
  ['] safe-save see-xt
  ['] restart see-xt
  ['] recover see-xt
  ['] rollback see-xt
  ['] repl see-xt
  ['] br-boot see-xt
  ['] br-node see-xt

  br-user-wordlist @ 0<> if
    br-user-wordlist see-vocabulary
  then

  br-old-type @ br-type-xt!
  br.!end ;

br-clear
br-nl-init
br-meta-path$ br-file-exists? if br-meta-load then
br-pin-registry-init
br-myforth-build
br-lkg-build
sp0 sp!
fp0 fp!

only forth definitions br-user
