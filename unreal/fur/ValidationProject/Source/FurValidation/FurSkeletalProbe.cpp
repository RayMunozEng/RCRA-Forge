#include "FurViewportProbe.h"
#include "Components/SkinnedMeshComponent.h"
#include "Engine/World.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "Rendering/SkinWeightVertexBuffer.h"
#include "RenderingThread.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

bool UFurViewportProbe::SaveSkinnedPose(USkinnedMeshComponent* Component, const FString& Filename)
{
#if WITH_EDITOR
 if (!IsValid(Component)) return false;
 auto* Data = Component->GetSkeletalMeshRenderData();
 auto* Weights = Component->GetSkinWeightBuffer(0);
 if (!Data || Data->LODRenderData.IsEmpty() || !Weights) return false;
 const auto& LOD = Data->LODRenderData[0];
 if (LOD.GetNumVertices() > 100000) return false;
 TArray<FMatrix44f> Matrices;
 Component->GetCurrentRefToLocalMatrices(Matrices, 0);
 TArray<TSharedPtr<FJsonValue>> Vertices, Indices;
 for (uint32 I=0; I<LOD.GetNumVertices(); ++I)
 {
  const FVector P=Component->GetComponentTransform().TransformPosition(FVector(USkinnedMeshComponent::GetSkinnedVertexPosition(Component,I,LOD,*Weights,Matrices)));
  TArray<TSharedPtr<FJsonValue>> V;
  V.Add(MakeShared<FJsonValueNumber>(P.X)); V.Add(MakeShared<FJsonValueNumber>(P.Y)); V.Add(MakeShared<FJsonValueNumber>(P.Z));
  Vertices.Add(MakeShared<FJsonValueArray>(V));
 }
 TArray<uint32> Raw; LOD.MultiSizeIndexContainer.GetIndexBuffer(Raw);
 for (uint32 I:Raw) Indices.Add(MakeShared<FJsonValueNumber>(I));
 auto Object=MakeShared<FJsonObject>(); Object->SetArrayField(TEXT("vertices"),Vertices);Object->SetArrayField(TEXT("indices"),Indices);
 FString Text;auto Writer=TJsonWriterFactory<>::Create(&Text);FJsonSerializer::Serialize(Object,Writer);
 return FFileHelper::SaveStringToFile(Text,*Filename);
#else
 return false;
#endif
}
void UFurViewportProbe::FlushPoseUpdates(USkinnedMeshComponent* Component)
{
#if WITH_EDITOR
 if (IsValid(Component) && Component->GetWorld()) { Component->GetWorld()->SendAllEndOfFrameUpdates();FlushRenderingCommands(); }
#endif
}
