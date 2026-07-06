from wordcount import count_words, main


def test_count_words_counts_whitespace_separated_tokens():
    assert count_words("the quick brown fox") == 4


def test_main_prints_word_count(tmp_path, capsys):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("one two three")
    main([str(file_path)])
    captured = capsys.readouterr()
    assert captured.out.strip() == "3"
