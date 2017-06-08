import click
import os
from shrinkfuzz.shrinker import Shrinker
import subprocess
import signal
import hashlib
import sys
import time
import binascii
import shutil


def signal_group(sp, signal):
    gid = os.getpgid(sp.pid)
    assert gid != os.getgid()
    os.killpg(gid, signal)


def interrupt_wait_and_kill(sp):
    if sp.returncode is None:
        # In case the subprocess forked. Python might hang if you don't close
        # all pipes.
        for pipe in [sp.stdout, sp.stderr, sp.stdin]:
            if pipe:
                pipe.close()
        try:
            signal_group(sp, signal.SIGINT)
            for _ in range(10):
                if sp.poll() is not None:
                    return
                time.sleep(0.1)
            signal_group(sp, signal.SIGKILL)
        except ProcessLookupError:
            return


@click.command()
@click.argument('command')
@click.argument('input')
@click.argument('output')
@click.option(
    '--corpus', default='corpus',
    type=click.Path(file_okay=False, resolve_path=True))
@click.option(
    '--timeout', default=5, type=click.FLOAT, help=(
        'Time out subprocesses after this many seconds. If set to <= 0 then '
        'no timeout will be used.'))
@click.option('--debug', default=False, is_flag=True, help=(
    'Emit (extremely verbose) debug output while shrinking'
))
def main(command, input, output, corpus, timeout, debug):

    crashes = os.path.join(corpus, "crashes")
    unstable = os.path.join(corpus, "unstable")
    timeouts = os.path.join(corpus, "timeouts")
    seeds = os.path.join(corpus, "seeds")
    exemplars = os.path.join(corpus, "exemplars")
    gallery = os.path.join(corpus, "gallery")
    for f in [crashes, seeds, unstable, timeouts, exemplars, gallery]:
        try:
            os.makedirs(f)
        except FileExistsError:
            pass

    def name_for(n):
        return '-'.join((n, input))

    def hashed_name(s):
        return name_for(hashlib.sha1(s).hexdigest()[:8])

    first_call = True

    def record_in(f, s):
        with open(os.path.join(f, hashed_name(s)), 'wb') as o:
            o.write(s)

    seen_contents = set()

    def classify(s):
        nonlocal first_call
        if first_call:
            target = sys.stdout
            first_call = False
        else:
            target = subprocess.DEVNULL

        try:
            os.unlink(output)
        except FileNotFoundError:
            pass

        with open(input, 'wb') as o:
            o.write(s)

        sp = subprocess.Popen(
            command, stdout=target, stdin=target,
            stderr=target, universal_newlines=False,
            preexec_fn=os.setsid, shell=True,
        )
        try:
            sp.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            record_in(timeouts, s)
            return ()
        finally:
            interrupt_wait_and_kill(sp)

        if sp.returncode < 0:
            record_in(crashes, s)
        results = set()
        results.add("return-%d" % (sp.returncode,))
        
        try:
            with open(output, 'rb') as i:
                output_contents = hashlib.sha1(i.read()).hexdigest()[:8]
        except FileNotFoundError:
            output_contents = None
        else:
            if output_contents not in seen_contents:
                gallery_file = os.path.join(
                    gallery, "%s-%s" % (
                    output_contents, os.path.basename(output)))
                shutil.copy(output, gallery_file)
                seen_contents.add(output_contents)
        results.add("output-%s" % (output_contents,))
        return results
        
    with open(input, 'rb') as i:
        initial = i.read()

    save_initial = os.path.join(corpus, name_for('initial'))
    if not os.path.exists(save_initial):
        with open(save_initial, 'wb') as o:
            o.write(initial)

    def corpus_path(s):
        return os.path.join(seeds, hashed_name(s))

    def added(s):
        with open(corpus_path(s), 'wb') as o:
            o.write(s)

    def removed(s):
        os.unlink(corpus_path(s))

    def best_changed(b, s):
        p = corpus_path(s)
        for r in b:
            target = os.path.join(exemplars, name_for(r))
            try:
                os.unlink(target)
            except FileNotFoundError:
                pass
            os.link(p, target)
            assert os.path.exists(target)

    def unstable_callback(s):
        record_in(unstable, s)

    shrinker = Shrinker(
        (initial,), classify, add_callback=added, remove_callback=removed,
        change_callback=best_changed, unstable_callback=unstable_callback,
        debug=debug,
    )

    if not shrinker.seen(b''):
        shrinker.classify(b'')

    for f in os.listdir(seeds):
        f = os.path.join(seeds, f)
        try:
            with open(f, 'rb') as i:
                s = i.read()
        except FileNotFoundError:
            continue
        if not shrinker.seen(s):
            os.unlink(f)
            shrinker.classify(s)

    shrinker.run()


if __name__ == '__main__':
    main.main(sys.args, standalone_mode=False)
