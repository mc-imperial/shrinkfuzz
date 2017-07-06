import hashlib
from collections import Counter, defaultdict
import sys


def seen_key(s):
    return int.from_bytes(hashlib.sha1(s).digest()[:4], 'big')


def sort_key(s):
    return (len(s), s)


class Shrinker(object):
    def __init__(
        self, initial_examples, classify,
        add_callback=None, remove_callback=None, change_callback=None,
        unstable_callback=None,
        debug=False,
    ):
        self.__classify = classify
        self.__seen = set()
        self.__exemplars = {}
        self.__best = defaultdict(set)
        self.__corpus = []
        self.__exhausted = set()
        self.__add_callback = add_callback or (lambda s: None)
        self.__remove_callback = remove_callback or (lambda s: None)
        self.__change_callback = change_callback or (lambda s: None)
        self.__unstable_callback = unstable_callback or (lambda s: None)
        self.__debug = debug
        for s in set(initial_examples):
            self.classify(s)

    def debug(self, *args, **kwargs):
        if self.__debug:
            print(*args, **kwargs, file=sys.stderr)

    def classify(self, s):
        assert not self.seen(s)
        assert not self.__best[s]
        self.mark_seen(s)
        result = self.__classify(s)

        # Guard quite aggressively against unstable classifications. If this
        # string would make it into the corpus, try twice more and make sure
        # we classify it the same way every time. If we don't, add it to the
        # unstable callback and omit it from consideration.
        if any((
            r not in self.__exemplars
            or sort_key(self.__exemplars[r]) > sort_key(s)) for r in result
        ):
            for _ in range(2):
                result2 = self.__classify(s)
                if result != result2:
                    self.__unstable_callback(s)
                    return ()

        improved = []
        for r in result:
            if r not in self.__exemplars:
                self.debug("Discovered new label %r" % (r,))
                self.__exemplars[r] = s
                self.__best[s].add(r)
            elif sort_key(s) < sort_key(self.__exemplars[r]):
                existing = self.__exemplars[r]
                improved.append(r)
                self.__exemplars[r] = s
                self.__best[s].add(r)
                self.__best[existing].remove(r)
                if not self.__best[existing]:
                    self.__corpus.remove(existing)
                    self.__exhausted.discard(existing)
                    self.__remove_callback(existing)

        if improved:
            self.debug("Improved labels %s to %d bytes" % (
                ', '.join(improved), len(s)))

        if self.__best[s]:
            self.__corpus.append(s)
            self.__add_callback(s)
            self.__change_callback(self.__best[s], s)
        return set(result) 

    def seen(self, s):
        return seen_key(s) in self.__seen

    def mark_seen(self, s):
        self.__seen.add(seen_key(s))

    def shrink(self, target, predicate):
        used_alphabet = set()

        while True:
            counts = Counter(target)
            available = [c for c in counts if c not in used_alphabet]
            if not available:
                break
            c = bytes([min(available, key=counts.__getitem__)])
            partition = partition_on(target, c)
            self.debug("Partitioning by %r into %d parts" % (c, len(partition)))
            used_alphabet.add(c[0])
            partition = self.shrink_sequence(
                partition, lambda ls: predicate(partition_to_string(
                    target, ls
                ))
            )
            target = partition_to_string(target, partition)

        self.debug("Partitioning bytewise")
        return self.shrink_sequence(target, predicate)

    def shrink_sequence(self, target, predicate):
        original = target

        def deletable(i, j):
            s = target[:i] + target[j:]
            assert len(s) < len(target)
            return predicate(s)

        i = 0
        while i < len(target):
            k = find_large_n(
                len(target) - i, lambda k: deletable(i, i + k))
            if k > 0:
                target = target[:i] + target[i + k:]
            i += 1
        return target

    def run(self):
        while len(self.__exhausted) < len(self.__corpus):
            target = max(
                [s for s in self.__corpus if s not in self.__exhausted],
                key=sort_key
            )
            objectives = list(self.__best[target])

            assert objectives
            if len(objectives) > 1:
                desc = 'any of %s' % (', '.join(objectives),)
            else:
                desc = objectives[0]

            self.debug("Shrinking %d bytes for %s" % (len(target), desc))

            original = target

            def predicate(t):
                assert len(t) < len(target)
                if self.seen(t):
                    return False
                markers = self.classify(t)
                for o in objectives:
                    if o in markers:
                        return True
                return False

            target = self.shrink(target, predicate)

            if target == original:
                self.__exhausted.add(target)
            else:
                self.debug("Shrink pass deleted %d bytes out of %d" % (
                    len(original) - len(target), len(original)
                ))


def find_large_n(max_n, f):
    if not f(1):
        return 0
    lo = 1
    hi = 2
    while hi <= max_n and f(hi):
        lo = hi
        hi *= 2
    if hi > max_n:
        if f(max_n):
            return max_n
        else:
            hi = max_n
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if f(mid):
            lo = mid
        else:
            hi = mid
    return lo


def partition_on(string, c):
    if not string:
        return []
    if isinstance(c, bytes):
        assert len(c) == 1
        c = c[0]
    partition = [[0, 1]]
    for i, d in enumerate(string):
        if i == 0:
            continue
        if d != c:
            partition[-1][-1] = i + 1
        else:
            partition.append([i, i + 1])
    assert partition[0][0] == 0
    assert partition[-1][-1] == len(string)
    for x, y in zip(partition, partition[1:]):
        assert x[1] == y[0]
    return partition


def partition_to_string(string, partition):
    result = bytearray()
    for u, v in partition:
        result.extend(string[u:v])
    return bytes(result)
