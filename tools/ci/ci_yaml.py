"""YAML parsing that rejects duplicate keys before normalization hides them."""
import yaml


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == 'tag:yaml.org,2002:merge':
                continue
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ValueError(f'Duplicate YAML key at line {key_node.start_mark.line + 1}')
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load(text):
    return yaml.load(text, Loader=UniqueKeyLoader)


def load_all(text):
    return yaml.load_all(text, Loader=UniqueKeyLoader)
