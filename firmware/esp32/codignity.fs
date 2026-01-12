decimal

\ Reload safety:
\ Re-sending this file repeatedly grows the dictionary until the ESP32 hard-faults.
\ We install a small anchor word (`cd-dev`) so each load can `forget` the previous codignity build.
only forth definitions
s" cd-dev" find 0<> [if] forget cd-dev [then]
: cd-dev ( -- ) ;  \ reload anchor (used by `forget` above)

\ ESP32forth hides many useful implementation words in the `internals` vocabulary.
\ We opt-in so we can build a quiet, protocol-first command loop.
only forth definitions also internals also interrupts

\ Computational Dignity protocol (ESP32 / ESP32forth)
\ TODO(thesis): Replace dummy sampling with real sensor read + timestamp source.
\ TODO(thesis): Persist history/source to flash (SPIFFS) and implement rollback.
\ TODO(thesis): Replace `bye`-based reboot with a clean ESP32 restart primitive.

vocabulary cd-user
' cd-user >body constant cd-user-wordlist

256 constant cd-fifo-size
create cd-fifo cd-fifo-size 2* cells allot  \ value, timestamp pairs

variable cd-head
variable cd-count
variable cd-tick

: cd-clear ( -- ) 0 cd-head ! 0 cd-count ! ;

: cd-min ( a b -- a|b ) 2dup < if drop else swap drop then ;
: cd-submod ( idx n mod -- idx' ) >r swap r@ + swap - r> mod ;
: cd-adv ( a n -- a' n' ) 1- swap 1+ swap ;
: cd-drop1 ( a n -- a' n' ) 1- swap 1+ swap ;
: cd-space? ( c -- f ) dup bl = over 9 = or over 10 = or swap 13 = or ;
: cd-skip-spaces ( a n -- a' n' )
  begin dup while over c@ cd-space? if cd-adv else exit then repeat ;

: cd-addr ( idx -- addr ) 2* cells cd-fifo + ;

: cd-write ( value ts idx -- )
  cd-addr dup cell+ >r
  over r@ !            \ ts -> addr+cell
  swap drop !          \ value -> addr
  r> drop ;

: cd-inc-count ( -- )
  cd-count @ cd-fifo-size < if cd-count @ 1+ cd-count ! then ;

: cd-push ( value ts -- )
  cd-head @ cd-write
  cd-head @ 1+ cd-fifo-size mod cd-head !
  cd-inc-count ;

: cd-read ( idx -- value ts ) cd-addr dup @ swap cell+ @ ;

: cd.!end ( -- ) ." ! end" cr ;
: cd.!ok ( -- ) ." ! ok" cr ;
: cd.!sample ( value ts -- ) ." ! " . . cr ;
: cd.# ( a n -- ) ." # " type cr ;

variable cd-error-emitted
: cd-error-reset ( -- ) 0 cd-error-emitted ! ;
: cd-error-on ( -- ) -1 cd-error-emitted ! ;
: cd.#err ( a n -- ) cd-error-on ." # err " type cr ;
: cd.#code ( n -- ) cd-error-on ." # code " . cr ;
: cd-consume-line ( -- ) #tib @ >in ! ;
: cd-rest-of-line ( -- a n )
  tib >in @ +  #tib @ >in @ - ;

: cd-next-ts ( -- u ) cd-tick @ dup 1+ cd-tick ! ;
: cd-next-sample ( -- value ts ) cd-next-ts dup ;

: 0<> ( n -- f ) 0= 0= ;
: 0> ( n -- f ) 0 > ;
: cd-exit postpone exit ; immediate

: 2swap ( a b c d -- c d a b ) rot >r rot r> ;
: 2over ( a b c d -- a b c d a b ) >r >r 2dup r> r> 2swap ;

: cd-parse-int-or ( default -- n )
  bl parse dup 0= if 2drop exit then
  rot drop evaluate ;

\ ------------------------------------------------------------
\ User vocabulary helpers

  \ NOTE: ESP32forth does not provide `search-wordlist` / `get-order`.
  \ For `define` we use `find` with a fixed search order (see `define`).

variable cd-define-current
: cd-define-current-save ( -- ) current @ cd-define-current ! ;
: cd-define-current-restore ( -- ) cd-define-current @ current ! ;

variable cd-define-la
variable cd-define-ln
variable cd-define-na
variable cd-define-nn

variable cd-token-a
variable cd-token-n
variable cd-token-len

: cd-token ( a n -- aTok nTok aRest nRest f )
  cd-skip-spaces
  dup 0= if 2drop 0 0 0 0 0 exit then
  2dup cd-token-n ! cd-token-a ! 2drop
  0 cd-token-len !
  cd-token-a @ cd-token-n @                           \ aCur nCur
  begin
    dup 0> if
      over c@ cd-space? 0=
    else
      0
    then
  while
    cd-adv
    1 cd-token-len +!
  repeat
  cd-token-a @ cd-token-len @ 2swap -1 ;

: cd-colon-token? ( a n -- f ) 1 = swap c@ [char] : = and ;
: cd-4drop ( a b c d -- ) 2drop 2drop ;
: cd-5drop ( a b c d e -- ) drop cd-4drop ;

\ Parse `: name ... ;` from a line and return the `name` token.
: cd-define-name ( a n -- a n f )
  cd-token dup 0= if cd-5drop 0 0 0 exit then drop             \ aTok nTok aR nR
  2over cd-colon-token? 0= if 2drop 2drop 0 0 0 exit then
  2swap 2drop                                                   \ aR nR
  cd-token dup 0= if cd-5drop 0 0 0 exit then drop              \ aName nName aR2 nR2
  2drop                                                         \ aName nName
  -1 ;

\ ------------------------------------------------------------
\ Files (SPIFFS) helpers

4 constant cd-safe-gpio  \ DOIT ESP32 DEVKIT V1: user wired button between GPIO4 and GND.

64 constant cd-path-max
create cd-myforth-path cd-path-max allot
variable cd-myforth-n

: cd-myforth-build ( -- )
  remember-filename dup cd-myforth-n ! cd-myforth-path swap cmove
  cd-myforth-path cd-myforth-n @ + 0 swap c! ;

: cd-myforth$ ( -- a n ) cd-myforth-path cd-myforth-n @ ;

64 constant cd-lkg-max
create cd-lkg-path cd-lkg-max allot
variable cd-lkg-n

: cd-lkg-build ( -- )
  cd-myforth$ dup cd-lkg-n ! cd-lkg-path swap cmove
  s" .lkg" cd-adv dup >r
  cd-lkg-path cd-lkg-n @ + swap cmove
  cd-lkg-n @ r@ + dup cd-lkg-n !
  cd-lkg-path + 0 swap c!
  r> drop ;

: cd-lkg$ ( -- a n ) cd-lkg-path cd-lkg-n @ ;

: cd-file-exists? ( a n -- f )
  r/o open-file dup 0<> if
    drop drop 0 exit
  then
  drop close-file drop -1 ;

\ ------------------------------------------------------------
: cd-dump ( n -- )
  dup 0= if drop cd.!end exit then
  dup >r
  cd-head @ r@ cd-fifo-size cd-submod
  r@ 0 ?do
    dup i + cd-fifo-size mod cd-read cd.!sample
  loop
  drop
  r> drop
  cd.!end ;

\ ------------------------------------------------------------
\ History (persistent, SPIFFS)

: cd-history-path$ ( -- a n ) s" /spiffs/codignity.history" ;
create cd-nl 1 allot
create cd-sp 1 allot

: cd-now ( -- u ) cd-next-ts ;

: cd-nl-init ( -- ) 10 cd-nl c! bl cd-sp c! ;

: cd-open-append ( a n -- fid )
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

: cd-write-nl ( fid -- ) cd-nl 1 rot write-file throw ;
: cd-write-space ( fid -- ) cd-sp 1 rot write-file throw ;
: cd-write-u ( u fid -- )
  >r <# #s #> r> write-file throw ;

160 constant cd-history-line-max
create cd-history-line cd-history-line-max allot
variable cd-history-ln
create cd-history-ch 1 allot

: cd-eol? ( c -- f ) dup 10 = swap 13 = or ;
: cd-history-line-clear ( -- ) 0 cd-history-ln ! ;
: cd-history-line-flush ( -- )
  cd-history-ln @ dup 0> if
    ." ! " cd-history-line swap type cr
  else
    drop
  then
  cd-history-line-clear ;

: cd-history-line-add ( c -- )
  cd-history-ln @ cd-history-line-max >= if cd-history-line-flush then
  cd-history-line cd-history-ln @ + c!
  1 cd-history-ln +! ;

: (cd-history-event) { a n -- }
  cd-history-path$ cd-open-append { fid }
  cd-now fid cd-write-u
  fid cd-write-space
  a n fid write-file throw
  fid cd-write-nl
  fid close-file throw ;

: (cd-history-event+) { ea en pa pn -- }
  cd-history-path$ cd-open-append { fid }
  cd-now fid cd-write-u
  fid cd-write-space
  ea en fid write-file throw
  pn 0<> if
    fid cd-write-space
    pa pn fid write-file throw
  then
  fid cd-write-nl
  fid close-file throw ;

: cd-history-event ( a n -- ) ['] (cd-history-event) catch drop ;
: cd-history-event+ ( ea en pa pn -- ) ['] (cd-history-event+) catch drop ;

: (cd-history-event-kv) { ea en ka kn va vn -- }
  cd-history-path$ cd-open-append { fid }
  cd-now fid cd-write-u
  fid cd-write-space
  ea en fid write-file throw
  fid cd-write-space
  ka kn fid write-file throw
  fid cd-write-space
  va vn fid write-file throw
  fid cd-write-nl
  fid close-file throw ;

: cd-history-event-kv ( ea en ka kn va vn -- ) ['] (cd-history-event-kv) catch drop ;

: history ( -- )
  cd-history-path$ r/o open-file dup 0<> if drop drop cd.!end exit then
  drop { fid }
  cd-history-line-clear
  begin
    cd-history-ch 1 fid read-file throw dup
  while
    drop
    cd-history-ch c@ dup cd-eol? if
      drop cd-history-line-flush
    else
      cd-history-line-add
    then
  repeat
  drop
  cd-history-line-flush
  fid close-file throw
  cd.!end ;

\ ------------------------------------------------------------
\ Metadata (persistent, SPIFFS)

: cd-meta-path$ ( -- a n ) s" /spiffs/codignity.meta" ;
16 constant cd-meta-max
16 constant cd-meta-key-max
32 constant cd-meta-val-max
cd-meta-key-max 1+ constant cd-meta-key-entry
cd-meta-val-max 1+ constant cd-meta-val-entry

create cd-meta-keys cd-meta-max cd-meta-key-entry * allot
create cd-meta-vals cd-meta-max cd-meta-val-entry * allot
variable cd-meta-count
variable cd-meta-tka
variable cd-meta-tkn
variable cd-meta-tva
variable cd-meta-tvn

: cd-meta-clear ( -- ) 0 cd-meta-count ! ;
: cd-meta-kaddr ( idx -- a ) cd-meta-key-entry * cd-meta-keys + ;
: cd-meta-vaddr ( idx -- a ) cd-meta-val-entry * cd-meta-vals + ;
: cd-meta-kread ( idx -- a n )
  cd-meta-kaddr dup c@ swap 1+ swap ;
: cd-meta-vread ( idx -- a n )
  cd-meta-vaddr dup c@ swap 1+ swap ;
: cd-meta-kwrite ( a n idx -- )
  cd-meta-kaddr >r
  cd-meta-key-max cd-min dup r@ c!
  r@ 1+ swap cmove
  r> drop ;
: cd-meta-vwrite ( a n idx -- )
  cd-meta-vaddr >r
  cd-meta-val-max cd-min dup r@ c!
  r@ 1+ swap cmove
  r> drop ;

: cd-meta-find { a n -- idx|-1 }
  cd-meta-count @ 0 ?do
    i cd-meta-kread a n str= if i unloop exit then
  loop
  -1 ;

: cd-meta-set { ka kn va vn -- ok? }
  ka kn cd-meta-find dup -1 <> if
    va vn rot cd-meta-vwrite
    -1 exit
  then
  drop
  cd-meta-count @ cd-meta-max >= if 0 exit then
  ka kn cd-meta-count @ cd-meta-kwrite
  va vn cd-meta-count @ cd-meta-vwrite
  cd-meta-count @ 1+ cd-meta-count !
  -1 ;

: (cd-meta-save) ( -- )
  cd-meta-path$ delete-file drop
  cd-meta-path$ w/o create-file throw { fid }
  cd-meta-count @ 0 ?do
    i cd-meta-kread fid write-file throw
    fid cd-write-space
    i cd-meta-vread fid write-file throw
    fid cd-write-nl
  loop
  fid close-file throw ;

: cd-meta-save ( -- ok? ) ['] (cd-meta-save) catch 0= ;

: cd-meta-load-buf ( a n -- )
  begin
    cd-token dup 0= if cd-5drop exit then drop            \ ka kn aR nR
    cd-token dup 0= if cd-5drop 2drop exit then drop      \ ka kn va vn aR2 nR2
    >r >r cd-meta-set drop r> r>
  again ;

: (cd-meta-load) ( -- )
  cd-meta-clear
  cd-meta-path$ r/o open-file dup 0<> if drop drop exit then
  drop { fid }
  fid file-size throw { size }
  size 0= if fid close-file throw exit then
  size allocate throw { buf }
  buf size fid read-file throw drop
  fid close-file throw
  buf size cd-meta-load-buf
  buf free throw ;

: cd-meta-load ( -- ) ['] (cd-meta-load) catch drop ;

\ Metadata lookup

: cd-meta-get$ ( ka kn -- va vn f )
  cd-meta-find dup -1 = if drop 0 0 0 exit then
  cd-meta-vread -1 ;

: cd-id$ ( -- a n )
  s" id" cd-meta-get$ dup if
    drop
  else
    drop 2drop
    s" smart"
  then ;

: cd-role$ ( -- a n )
  s" role" cd-meta-get$ dup if
    drop
  else
    drop 2drop
    s" smart"
  then ;

: cd-ver$ ( -- a n )
  s" ver" cd-meta-get$ dup if
    drop
  else
    drop 2drop
    s" codignity-0.1"
  then ;

: cd-children$ ( -- a n )
  s" children" cd-meta-get$ dup if
    drop
  else
    drop 2drop
    s" 0"
  then ;

: cd.!meta-if { ka kn la ln -- }
  ka kn cd-meta-get$ dup if
    drop
    ." ! " la ln type space type cr
  else
    drop 2drop
  then ;

: meta ( -- )
  cd-rest-of-line cd-skip-spaces
  cd-consume-line
  dup 0= if
    2drop
    cd-meta-count @ 0 ?do
      ." ! " i cd-meta-kread type space i cd-meta-vread type cr
    loop
    cd.!end
    exit
  then
  cd-token dup 0= if cd-5drop s" meta_syntax" cd.#err cd.!end exit then drop  \ ka kn aR nR
  2swap cd-skip-spaces 2swap                                                     \ ka kn aR' nR'
  dup 0= if                                                                      \ meta <key>
    2drop
    2dup cd-meta-find dup -1 = if
      drop 2drop
      s" meta_missing" cd.#err cd.!end exit
    then
    >r
    ." ! " 2dup type space
    r> cd-meta-vread type cr
    2drop
    cd.!end
    exit
  then
  cd-token dup 0= if cd-5drop 2drop s" meta_syntax" cd.#err cd.!end exit then drop  \ ka kn va vn aR2 nR2
  cd-skip-spaces dup 0<> if
    2drop 2drop 2drop
    s" meta_syntax" cd.#err cd.!end exit
  then
  2drop                                                                            \ ka kn va vn
  2dup cd-meta-tvn ! cd-meta-tva !                                                 \ stash value
  2swap 2dup cd-meta-tkn ! cd-meta-tka ! 2swap                                     \ stash key
  cd-4drop
  cd-meta-tka @ cd-meta-tkn @ cd-meta-tva @ cd-meta-tvn @ cd-meta-set 0= if
    s" meta_full" cd.#err cd.!end exit
  then
  cd-meta-save 0= if
    s" meta_io" cd.#err cd.!end exit
  then
  s" meta" cd-meta-tka @ cd-meta-tkn @ cd-meta-tva @ cd-meta-tvn @ cd-history-event-kv
  cd.!ok
  cd.!end ;

\ Protocol commands (match PROTOCOL_REFERENCE.md)

: ? ( -- )
  ." ! id " cd-id$ type cr
  ." ! role " cd-role$ type cr
  ." ! mcu esp32" cr
  ." ! ver " cd-ver$ type cr
  ." ! fifo " cd-fifo-size . cr
  s" units" 2dup cd.!meta-if
  s" pins" 2dup cd.!meta-if
  ." ! children " cd-children$ type cr
  cd.!end ;

: s ( -- )
  cd-next-sample 2dup cd-push cd.!sample
  cd.!end ;

: n ( -- )
  ." ! " cd-count @ . cr
  cd.!end ;

: d ( -- )
  cd-count @ cd-parse-int-or
  cd-count @ cd-min
  cd-dump ;

: c ( -- )
  cd-clear
  cd.!ok
  cd.!end ;

: explain ( -- )
  ." ! id " cd-id$ type cr
  ." ! role " cd-role$ type cr
  ." ! mcu esp32" cr
  ." ! ver " cd-ver$ type cr
  s" units" 2dup cd.!meta-if
  s" pins" 2dup cd.!meta-if
  ." ! children " cd-children$ type cr
  ." ! fifo " cd-fifo-size . cr
  ." ! core ? s n d c" cr
  ." ! extended explain source history define meta save validate safe-save restart recover rollback repl" cr
  cd.!end ;

: cd-validate? ( -- f )
  depth dup 0= swap -1 = or
  fdepth 0= and ;

: validate ( -- )
  cd-validate? if
    cd.!ok
  else
    ." ! fail stack" cr
  then
  cd.!end ;

: define ( -- )
  cd-rest-of-line cd-skip-spaces
  2dup cd-define-ln ! cd-define-la ! 2drop
  cd-define-la @ cd-define-ln @ cd-define-name 0= if
    s" define_syntax" cd.#err cd.!end cd-consume-line 2drop cd-exit
  then
  2dup cd-define-nn ! cd-define-na !
  2drop

  \ Reject redefining any existing word (new words only).
  cd-define-na @ cd-define-nn @ find 0<> if
    s" define_exists" cd.#err cd.!end cd-consume-line cd-exit
  then

  s" define" cd-define-na @ cd-define-nn @ cd-history-event+
  cd-consume-line
  cd-define-current-save
  cd-user-wordlist current !
  cd-define-la @ cd-define-ln @ evaluate
  cd-define-current-restore
  cd.!ok
  cd.!end ;

\ ------------------------------------------------------------
\ Protocol-mode loop + error handling

: cd-route ( a n -- )
  \ TODO(thesis): Implement routing to child nodes over UART/RS-485.
  s" route_unimplemented" cd.#err
  ." # target " type cr
  cd.!end ;

: cd-notfound ( a n f -- )
  0= if 2drop exit then
  2dup over c@ [char] @ = if
    cd-drop1 cd-route
    cd-consume-line
    2drop
    exit
  then
  s" notfound" cd.#err
  2dup cd.#
  cd.!end
  cd-consume-line
  2drop ;

: cd-handle-exception ( n -- )
  cd-error-emitted @ if drop cd-error-reset exit then
  s" exception" cd.#err
  cd.#code
  cd.!end
  cd-error-reset ;

variable cd-exit
variable cd-old-echo
variable cd-old-arrow
variable cd-old-notfound

: repl ( -- )
  -1 cd-old-echo !
  -1 cd-old-arrow !
  -1 cd-exit !
  -1 echo !
  -1 arrow !
  cd.!ok
  cd.!end ;

: cd-node ( -- )
  echo @ cd-old-echo !
  arrow @ cd-old-arrow !
  'notfound @ cd-old-notfound !

  0 cd-exit !
  0 echo !
  0 arrow !
  cd-error-reset
  ['] cd-notfound 'notfound !
  begin
    cd-exit @ 0<> if
      -1
    else
      refill 0= if
        10 ms
      else
        ['] evaluate-buffer catch ?dup if
          0 state ! sp0 sp! fp0 fp! rp0 rp!
          cd-handle-exception
        then
      then
      0
    then
  until
  cd-old-notfound @ 'notfound !
  cd-old-echo @ echo !
  cd-old-arrow @ arrow ! ;

: cd-safe-setup ( -- )
  cd-safe-gpio INPUT pinMode
  cd-safe-gpio gpio_pullup_en drop ;

: cd-safe-pressed? ( -- f ) cd-safe-gpio digitalRead 0= ;

: cd-boot ( -- )
  cd-safe-setup
  cd-safe-pressed? if
    -1 echo !
    -1 arrow !
    ." SAFE: pressed; staying in REPL" cr
  else
    cd-node
  then ;

: cd-ensure-autostart ( -- ) ['] cd-boot 'cold ! ;

: save ( -- )
  \ Persist the current image to /spiffs/myforth and keep protocol auto-start enabled.
  cd-ensure-autostart
  remember
  s" save" cd-history-event
  cd.!ok
  cd.!end ;

: safe-save ( -- )
  cd-validate? if
    cd-ensure-autostart
    cd-lkg$ save-name
    remember
    s" safe-save" cd-history-event
    cd.!ok
  else
    ." ! fail validate" cr
  then
  cd.!end ;

: restart ( -- )
  ." ! rebooting" cr
  cd.!end
  s" restart" cd-history-event
  100 ms
  bye ;

: recover ( -- )
  \ Factory reset: delete saved images and reboot.
  s" recover" cd-history-event
  cd-myforth$ delete-file drop
  cd-lkg$ delete-file drop
  cd.!ok
  cd.!end
  100 ms
  bye ;

: rollback ( -- )
  \ Minimal rollback: restore last-known-good image (myforth.lkg).
  1 cd-parse-int-or dup 1 <> if
    drop s" unsupported" cd.#err cd.!end exit
  then
  drop
  cd-lkg$ cd-file-exists? 0= if
    s" rollback_missing" cd.#err cd.!end exit
  then
  s" rollback" cd-history-event
  cd.!ok
  cd.!end
  cd-lkg$ restore-name ;

\ Source: decompile key words, prefixing each output line with "! ".
variable cd-old-type
variable cd-line-start
create cd-ch 1 allot

: cd-type-xt@ ( -- xt ) ['] type >body @ ;
: cd-type-xt! ( xt -- ) ['] type >body ! ;
: cd-raw-type ( a n -- ) cd-old-type @ execute ;
: cd-raw-emit ( c -- ) cd-ch c! cd-ch 1 cd-raw-type ;
: cd-prefix ( -- ) s" ! " cd-raw-type ;
: cd-type-prefixed ( a n -- )
  begin dup while
    over c@ dup 13 = over 10 = or if
      cd-raw-emit -1 cd-line-start !
    else
      cd-line-start @ if cd-prefix 0 cd-line-start ! then
      cd-raw-emit
    then
    cd-adv
  repeat 2drop ;

: source ( -- )
  cd-type-xt@ cd-old-type !
  ['] cd-type-prefixed cd-type-xt!
  -1 cd-line-start !

  ['] ? see-xt
  ['] s see-xt
  ['] n see-xt
  ['] d see-xt
  ['] c see-xt
  ['] explain see-xt
  ['] history see-xt
  ['] define see-xt
  ['] meta see-xt
  ['] save see-xt
  ['] validate see-xt
  ['] safe-save see-xt
  ['] restart see-xt
  ['] recover see-xt
  ['] rollback see-xt
  ['] repl see-xt
  ['] cd-boot see-xt
  ['] cd-node see-xt

  cd-user-wordlist @ 0<> if
    cd-user-wordlist see-vocabulary
  then

  cd-old-type @ cd-type-xt!
  cd.!end ;

cd-clear
cd-nl-init
cd-meta-load
cd-myforth-build
cd-lkg-build
sp0 sp!
fp0 fp!

only forth definitions cd-user
