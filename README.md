# inciser

Python script to use the xTool D1 Pro laser engraver for incising timber.
The idea is to drill small holes into wood so that it can be impregnated better.

As xTool engravers lack the dwell command (G4), we need to run the
engraver synchronously, meaning we time and wait for it to move and burn
and only issue the next command once it has completed the previous.

This script is quite hackish but does the job.

There are no command line arguments or interactivity, you need to build
the program by hand instead.

On an xTool D1 Pro 20W I can burn about three 5-15mm holes per second.

If I did this project again I'd probably try to get a different engraver.
xTool has their own proprietary firmware and only supports a subset of
GRBL codes.
