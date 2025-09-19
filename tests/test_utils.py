from rancher_helm_exporter.utils import StringUtils

def test_slugify():
    assert StringUtils.slugify("hello world") == "hello-world"
    assert StringUtils.slugify("hello-world") == "hello-world"
    assert StringUtils.slugify("hello_world") == "hello-world"
    assert StringUtils.slugify("hello.world") == "hello.world"
    assert StringUtils.slugify("hello world 123") == "hello-world-123"
    assert StringUtils.slugify(" a b c ") == "a-b-c"
    assert StringUtils.slugify("!@#$%^&*()+") == ""
    assert StringUtils.slugify("-") == ""
    assert StringUtils.slugify(".") == "."
