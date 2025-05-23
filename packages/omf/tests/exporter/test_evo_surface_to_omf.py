#  Copyright © 2025 Bentley Systems, Incorporated
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#      http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import tempfile
from os import path
from unittest import TestCase
from uuid import uuid4

import omf
import pyarrow as pa
from evo_schemas.components import (
    ContinuousAttribute_V1_0_1,
    ContinuousAttribute_V1_1_0,
    EmbeddedTriangulatedMesh_V2_0_0_Parts,
    Triangles_V1_1_0,
    Triangles_V1_1_0_Indices,
    Triangles_V1_1_0_Vertices,
)
from evo_schemas.elements import IndexArray1_V1_0_1, IndexArray2_V1_0_1
from evo_schemas.objects import (
    TriangleMesh_V2_0_0,
    TriangleMesh_V2_1_0,
)

from evo.data_converters.common import EvoWorkspaceMetadata, create_evo_object_service_and_data_client
from evo.data_converters.omf.exporter import export_omf_surface
from evo.data_converters.omf.importer import convert_omf


class TestExportOMFSurface(TestCase):
    def setUp(self) -> None:
        self.cache_root_dir = tempfile.TemporaryDirectory()
        self.workspace_metadata = EvoWorkspaceMetadata(workspace_id=str(uuid4()), cache_root=self.cache_root_dir.name)

        _, self.data_client = create_evo_object_service_and_data_client(self.workspace_metadata)

        # Convert an OMF file to Evo and use the generated Parquet files to test the exporter
        omf_file = path.join(path.dirname(__file__), "../data/surface_v1.omf")
        self.evo_objects = convert_omf(
            filepath=omf_file, evo_workspace_metadata=self.workspace_metadata, epsg_code=32650
        )

    def test_should_create_expected_omf_surface_element(self) -> None:
        evo_object = self.evo_objects[5]
        self.assertIsInstance(evo_object, TriangleMesh_V2_1_0)

        evo_object.description = "any description"
        element = export_omf_surface(uuid4(), None, evo_object, self.data_client)

        self.assertEqual(element.name, evo_object.name)
        self.assertEqual(element.description, evo_object.description)

        self.assertIsInstance(element.geometry, omf.SurfaceGeometry)

        self.assertEqual(len(element.geometry.vertices), 100)

        vertex = element.geometry.vertices[0]
        self.assertAlmostEqual(vertex[0], 0.55854415)
        self.assertAlmostEqual(vertex[1], 0.12844872)
        self.assertAlmostEqual(vertex[2], 0.13269596)

    def test_should_create_expected_omf_vertex_attributes(self) -> None:
        evo_object = self.evo_objects[5]
        self.assertIsInstance(evo_object, TriangleMesh_V2_1_0)

        element = export_omf_surface(uuid4(), None, evo_object, self.data_client)

        self.assertEqual(len(element.data), 1)

        scalar_data = element.data[0]

        self.assertIsInstance(scalar_data, omf.ScalarData)
        self.assertEqual(scalar_data.location, "vertices")
        self.assertEqual(scalar_data.name, "data assigned to vertices")

        self.assertEqual(len(scalar_data.array), 100)
        self.assertAlmostEqual(scalar_data.array[0], 0.06727262)
        self.assertAlmostEqual(scalar_data.array[1], 0.25991388)

    def test_should_create_expected_omf_face_attributes(self) -> None:
        evo_object = self.evo_objects[6]
        self.assertIsInstance(evo_object, TriangleMesh_V2_1_0)

        element = export_omf_surface(uuid4(), None, evo_object, self.data_client)

        self.assertEqual(len(element.data), 1)

        scalar_data = element.data[0]

        self.assertIsInstance(scalar_data, omf.ScalarData)
        self.assertEqual(scalar_data.location, "faces")
        self.assertEqual(scalar_data.name, "data assigned to faces")

        self.assertEqual(len(scalar_data.array), 50)
        self.assertAlmostEqual(scalar_data.array[0], 0.30219228)
        self.assertAlmostEqual(scalar_data.array[1], 0.44245225)

    def test_should_create_expected_omf_surface_element_from_old_object_schema(self) -> None:
        triangle_mesh_object = self.evo_objects[5]
        self.assertIsInstance(triangle_mesh_object, TriangleMesh_V2_1_0)

        continuous_attribute = triangle_mesh_object.triangles.vertices.attributes[0]
        self.assertIsInstance(continuous_attribute, ContinuousAttribute_V1_1_0)

        old_continuous_attribute = ContinuousAttribute_V1_0_1(
            name=continuous_attribute.name,
            values=continuous_attribute.values,
            nan_description=continuous_attribute.nan_description,
        )

        evo_object = TriangleMesh_V2_0_0(
            name=triangle_mesh_object.name,
            description="any description",
            uuid=None,
            bounding_box=triangle_mesh_object.bounding_box,
            coordinate_reference_system=triangle_mesh_object.coordinate_reference_system,
            triangles=Triangles_V1_1_0(
                vertices=Triangles_V1_1_0_Vertices(
                    **{**triangle_mesh_object.triangles.vertices.as_dict(), "attributes": [old_continuous_attribute]}
                ),
                indices=Triangles_V1_1_0_Indices(
                    **{**triangle_mesh_object.triangles.indices.as_dict(), "attributes": []}
                ),
            ),
        )

        element = export_omf_surface(uuid4(), None, evo_object, self.data_client)

        self.assertEqual(element.name, evo_object.name)
        self.assertEqual(element.description, evo_object.description)

        self.assertIsInstance(element.geometry, omf.SurfaceGeometry)

        self.assertEqual(len(element.geometry.vertices), 100)

        self.assertEqual(len(element.data), 1)

        scalar_data = element.data[0]
        self.assertIsInstance(scalar_data, omf.ScalarData)
        self.assertEqual(scalar_data.location, "vertices")
        self.assertEqual(scalar_data.name, "data assigned to vertices")

        self.assertEqual(len(scalar_data.array), 100)

    def test_should_unpack_chunked_triangles(self) -> None:
        evo_object = self.evo_objects[6]

        start_segment_index = 25
        number_of_segments = 10

        chunks_schema = pa.schema(
            [
                pa.field("start_segment_index", pa.uint64()),
                pa.field("number_of_segments", pa.uint64()),
            ]
        )
        chunks_table = pa.Table.from_pydict(
            {
                "start_segment_index": [start_segment_index],
                "number_of_segments": [number_of_segments],
            },
            schema=chunks_schema,
        )
        chunks_data = self.data_client.save_table(chunks_table)
        chunks = IndexArray2_V1_0_1(**chunks_data)

        evo_object.parts = EmbeddedTriangulatedMesh_V2_0_0_Parts(chunks=chunks)

        element = export_omf_surface(uuid4(), None, evo_object, self.data_client)

        self.assertEqual(len(element.geometry.vertices), 100)
        self.assertEqual(len(element.geometry.triangles), number_of_segments)

    def test_should_unpack_indexed_and_chunked_triangles(self) -> None:
        evo_object = self.evo_objects[6]

        start_segment_index = 5
        number_of_segments = 5

        chunks_schema = pa.schema(
            [
                pa.field("start_segment_index", pa.uint64()),
                pa.field("number_of_segments", pa.uint64()),
            ]
        )
        chunks_table = pa.Table.from_pydict(
            {
                "start_segment_index": [start_segment_index],
                "number_of_segments": [number_of_segments],
            },
            schema=chunks_schema,
        )
        chunks_data = self.data_client.save_table(chunks_table)
        chunks = IndexArray2_V1_0_1(**chunks_data)

        indices_schema = pa.schema(
            [
                pa.field("index", pa.uint64()),
            ]
        )
        indices_table = pa.Table.from_pydict(
            {"index": [0, 5, 10, 15, 20, 25, 30, 35, 40, 45]},
            schema=indices_schema,
        )
        indices_data = self.data_client.save_table(indices_table)
        indices = IndexArray1_V1_0_1(**indices_data)

        evo_object.parts = EmbeddedTriangulatedMesh_V2_0_0_Parts(chunks=chunks, triangle_indices=indices)

        element = export_omf_surface(uuid4(), None, evo_object, self.data_client)

        self.assertEqual(len(element.geometry.vertices), 100)
        self.assertEqual(len(element.geometry.triangles), number_of_segments)
