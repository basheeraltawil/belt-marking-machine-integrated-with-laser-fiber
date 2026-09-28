from glob import glob

from setuptools import find_packages, setup

package_name = 'belt_marking_gazebo'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name + '/worlds', glob('worlds/*.sdf')),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Basheer Al-Tawil',
    maintainer_email='basheeraltaweel@gmail.com',
    description='Gazebo Fortress world and kinematic digital twin of the belt marking machine.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'gz_twin_node = belt_marking_gazebo.gz_twin_node:main',
        ],
    },
)
