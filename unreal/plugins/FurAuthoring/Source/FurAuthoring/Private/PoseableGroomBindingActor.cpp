#include "PoseableGroomBindingActor.h"

#include "Components/PoseableMeshComponent.h"

APoseableGroomBindingActor::APoseableGroomBindingActor()
{
    PoseMesh = CreateDefaultSubobject<UPoseableMeshComponent>(TEXT("PoseMesh"));
    SetRootComponent(PoseMesh);
    PoseMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    PoseMesh->SetGenerateOverlapEvents(false);
    PoseMesh->SetCanEverAffectNavigation(false);
}
