from src.log import logger
import xml.etree.ElementTree as ET


def parse_xml(xml):
    return ET.fromstring(xml)


def get_ratio(root1, root2):
    # 获取比例，假设树的第一个节点具有合理的比例
    node1 = root1.find('.//node')
    node2 = root2.find('.//node')
    ratio = get_bounds(node1)[2] / get_bounds(node2)[2]
    return ratio


def get_bounds(node):
    return [int(i) for i in node.attrib['bounds'].replace("[", ",").replace("]", "").split(',') if i]


def scale_bounds(bounds, ratio):
    return [int(coord * ratio) for coord in bounds]


def compare_bounds(bounds1, bounds2, tolerance=10):
    ret = all(abs(b1 - b2) <= tolerance for b1, b2 in zip(bounds1, bounds2))
    return ret


def compare_nodes(node1, node2, ratio):
    bounds1 = get_bounds(node1)
    bounds2 = get_bounds(node2)
    scaled_bounds2 = scale_bounds(bounds2, ratio)
    return compare_bounds(bounds1, scaled_bounds2)


def compare_attributes(node1, node2):
    attrib1 = node1.attrib
    attrib2 = node2.attrib
    for key, value in attrib1.items():
        if key not in ['bounds', 'index']:
            if attrib2.get(key) != value:
                return False
    return True


def compare_recursive(node1, node2, ratio):
    if not compare_attributes(node1, node2):
        return False
    if not compare_nodes(node1, node2, ratio):
        return False

    children1 = list(node1)
    children2 = list(node2)

    # 牛奶max和6pro同样在搜索页但显示异常
    # if len(children1) != len(children2):
    #     return False

    return True


def compare_screens(*xml_strings):
    roots = [parse_xml(xml) for xml in xml_strings]
    differences = []

    for node1 in roots[0].iter('node'):
        matched = False
        for root in roots[1:]:
            for node2 in root.iter('node'):
                ratio = get_ratio(roots[0], root)
                if compare_recursive(node1, node2, ratio):
                    matched = True
                    break
            if matched:
                break
        if not matched:
            differences.append(node1)

    if len(differences) > 0:
        for xml in xml_strings:
            logger.info(xml)

    return [get_bounds(node) for node in differences]


if __name__ == '__main__':
    file1 = r"D:\test\dump.xml"
    file2 = r"D:\test\dump1.xml"
    with open(file1, 'r', encoding='utf8') as f1:
        xml1 = f1.read()
    with open(file2, 'r', encoding='utf8') as f2:
        xml2 = f2.read()

    _differences = compare_screens(xml1, xml2)
    for diff in _differences:
        print(diff)
