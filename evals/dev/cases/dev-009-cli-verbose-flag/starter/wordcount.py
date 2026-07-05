import argparse
import sys


def count_words(text):
    return len(text.split())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Count words in a file.")
    parser.add_argument("path", help="path to the text file")
    args = parser.parse_args(argv)

    with open(args.path) as f:
        text = f.read()

    print(count_words(text))


if __name__ == "__main__":
    main(sys.argv[1:])
