"""全ジョイントの segmentScaleCompensate を無効化するツール。"""

import mlib


def main():
    """シーン内ジョイントの segmentScaleCompensate を一括で OFF にします。"""
    joints = mlib.ls(type='joint')

    for j in joints:
        if j.hasAttr('segmentScaleCompensate'):
            j.setSegmentScaleCompensate(False)

    print(u'Turned off segmentScaleCompensate on {} joints.'.format(len(joints)))

if __name__ == '__main__':
    main()