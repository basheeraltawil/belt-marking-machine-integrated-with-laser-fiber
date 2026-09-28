from glob import glob

from setuptools import find_packages, setup

package_name = 'belt_marking_description'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name + '/urdf', glob('urdf/*.xacro')),
        ('share/' + package_name + '/rviz', glob('rviz/*.rviz')),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Basheer Al-Tawil',
    maintainer_email='basheeraltaweel@gmail.com',
    description='URDF/xacro model, RViz config and joint animation of the machine.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'joint_state_node = belt_marking_description.joint_state_node:main',
        ],
    },
)
