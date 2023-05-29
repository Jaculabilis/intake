{ pkgs ? import <nixpkgs> {} }:

let
  pypkgs = pkgs.python38Packages;
in pypkgs.buildPythonPackage {
  name = "intake";
  src = builtins.path { path = ./.; name = "intake"; };
  format = "pyproject";
  propagatedBuildInputs = with pypkgs; [ setuptools ];
}
