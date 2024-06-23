# inciser

Python script to use the xTool D1 Pro laser engraver for incising timber
Idea is to drill small holes into the wood so it can be impregnated better.

As xTool engravers lack the dwell command (G4), we need to run the
engraver synchronously, meaning we time and wait for it to move and burn
and only issue the next command once it is done.

This script is quite hackish but does the job

There are no arguments, you need to build the program by hand instead

On an xTool D1 Pro 20W I can burn about three 15mm holes per second

If I did this again I'd probably try to get a different engraver.

