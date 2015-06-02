# Copyright 2014 Google Inc. All Rights Reserved.
"""A utility for generating Windows Server passwords.

The requirements for the passwords are outlined in
http://technet.microsoft.com/en-us/library/cc786468(v=ws.10).aspx.
"""

import random
import string

_LENGTH = 12
_CHARACTER_CLASSES = [
    string.ascii_uppercase,
    string.ascii_lowercase,
    string.digits,
    r"""~!@#$%^&*_-+=`|\(){}[]:;"'<>,.?/""",
]
_CLASSES_REQUIRED = 3


def Generate(rand=None):
  """Returns a random password compatible with a Windows Server.

  Args:
    rand: A random-like object. This is useful for testing. If not
      specified, random.SystemRandom() is used which uses the OS CSPRNG.

  Returns:
    A password as a string.
  """
  rand = rand or random.SystemRandom()

  # Generate a password where each character is chosen uniformly at random from
  # the list of all characters. Repeat until the password meets the complexity
  # requirements. Each iteration has a 99.3% chance to succeed.
  #
  # Justification for the 99.3% claim:
  #   import itertools
  #
  #   # Sizes of the character classes.
  #   # Digits, uppercase, lowercase, punctuation.
  #   class_sizes = [10, 26, 26, 32]
  #
  #   # How many passwords use exactly one class?
  #   exactly_one = sum([x ** 12 for x in class_sizes])
  #
  #   # How many passwords use exactly two classes?  For each unique (unordered)
  #   # pair of classes, take the number of passwords that can be formed from
  #   # only those two classes, then subtract the number of those passwords that
  #   # only use one class or the other.
  #   exactly_two = (
  #       sum((class_sizes[a] + class_sizes[b]) ** 12 -
  #               class_sizes[a] ** 12 - class_sizes[b] ** 12
  #           for (a, b) in itertools.combinations(xrange(4), 2)))
  #
  #   # How many total passwords can be created?
  #   total = sum(class_sizes) ** 12
  #
  #   # What proportion of passwords contain fewer than three classes?
  #   invalid = (exactly_one + exactly_two) / float(total)
  #
  #   # ... meaning chance of success per iteration is?
  #   print(1 - invalid)  # 0.99301091742
  #
  # What's the chance we succeed in five or fewer tries?
  #   print(1 - invalid ** 5)  # 0.999999999983
  #
  # ... or ten?
  #   print(1 - invalid ** 10)  # 1.0 (exceeds precision of double)

  all_chars = ''.join(_CHARACTER_CLASSES)
  classes_represented = 0
  while classes_represented < _CLASSES_REQUIRED:
    candidate = [rand.choice(all_chars) for _ in xrange(_LENGTH)]
    candidate_chars = set(candidate)
    classes_represented = sum(not candidate_chars.isdisjoint(chars)
                              for chars in _CHARACTER_CLASSES)
  return ''.join(candidate)

if __name__ == '__main__':
  print Generate()
