# shrinkfuzz

shrinkfuzz is a small prototype fuzzer that works on the principle that
[test case reduction is surprisingly good at fuzzing](https://blog.regehr.org/archives/1284).


## Usage

Recommended usage is within a virtualenv:

```bash
virtualenv --python=python3 venv
source venv/bin/activate
pip install -e .
```

You can then use it as follows:

```bash
shrinkfuzz {cmd} {input} {output}
```

Where cmd is a command to run (it can be a longer shell string), input is
the file to start fuzzing from and output is the output file to consider. The
input file will be repeatedly modified and the command then called again to
observe the results.

Data will be put in the directory 'corpus' (this can be overridden by passing
the option `--corpus=some_other_dir`.

Within that directory there are various subdirectories. The ones most of
interest are:

* `crashes` contains any files that caused the program to exit with a signal
  return code (i.e. anything > 127 or < 0 depending on whether you interpret
  it with a sign bit)
* `timeouts` contains any files that caused the program to take more than the
  specified number of seconds.
* `unstable` contains any files that produced different results on different
  invocations.

## Approach

The key idea is to use multi-objective shrinking to try to find interesting
examples as we reduce, which leads to seed inputs for further fuzzing when
we discover new behaviour.

We consider "tags" which classify a given file. Right now the only two tags
are output (hashed) and return code. Long-term we will probably want to add
coverage metrics in there.

For each label we track the best (shortlex minimal) string that we've seen
exhibit it, and the set of all strings that are the best for at least one
label.

We then repeatedly iterate on the following loop:

1. Pick the worst (shortlex maximal) string in our corpus of strings that are
   best for at least one, that have not been marked as finished (initially no
   strings are marked as finished)
2. Perform a single pass of shrinking on it, with the condition being that it
   continues to exhibit at least one of the labels for which it was best at the
   start of the loop.
3. If that didn't produce any shrinks, mark the string as finished.


The shrink algorithm we use is a variant of the one used in
[structureshrink](https://github.com/DRMacIver/structureshrink) that has been
modified to take less time per pass but more time overall by removing a lot of
the smarter logic (so that it exhibits better spray as it shrinks).

In addition to this, whenever an example exhibits one of the following
behaviours it is removed from consideration (returns an empty set of tags)
but saved for later consideration by a user:

1. Calling it times out (the default timeout is 5 seconds)
2. Exits with a return code that indicates it was killed by a signal (e.g.
   assertion error or segfault)
3. Produces unstable results (fails to return the same exact tags on three
   distinct calls).
