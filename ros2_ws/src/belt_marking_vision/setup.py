from glob import glob

from setuptools import find_packages, setup

package_name = 'belt_marking_vision'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        # project docs for the offline assistant (docs -> ../../../docs symlink)
        ('share/' + package_name + '/docs', glob('docs/*.md')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Basheer Al-Tawil',
    maintainer_email='basheeraltaweel@gmail.com',
    description='Optional AI: vision QA, cycle-time anomaly detection, docs assistant, NL jobs.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'vision_qa_node = belt_marking_vision.vision_qa_node:main',
            'anomaly_node = belt_marking_vision.anomaly_node:main',
            'assistant = belt_marking_vision.assistant:main',
        ],
    },
)
